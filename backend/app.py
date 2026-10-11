from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sys
import time
from contextlib import contextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, unquote, urlsplit
from wsgiref.simple_server import make_server

import mysql.connector
from mysql.connector import IntegrityError, MySQLConnection


BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
TOKEN_LIFETIME_SECONDS = 60 * 60 * 12
PASSWORD_ITERATIONS = 310_000
MAX_REQUEST_BYTES = 1_000_000


def load_environment_file() -> None:
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        return

    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        value = value.strip().strip("\"'")
        os.environ.setdefault(key.strip(), value)


load_environment_file()

APP_SECRET_KEY = os.environ.get("APP_SECRET_KEY", "Jerrin@!1530")
def get_database_config() -> dict[str, Any]:
    db_url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("MYSQL_URL")
        or os.environ.get("MYSQL_PRIVATE_URL")
    )
    if db_url and "://" in db_url:
        parsed = urlsplit(db_url)
        return {
            "host": parsed.hostname or "127.0.0.1",
            "port": int(parsed.port or 3306),
            "database": parsed.path.lstrip("/") or "AgricultureDB",
            "user": unquote(parsed.username or ""),
            "password": unquote(parsed.password or ""),
            "connection_timeout": 5,
        }
    return {
        "host": os.environ.get("DB_HOST") or os.environ.get("MYSQLHOST", "127.0.0.1"),
        "port": int(os.environ.get("DB_PORT") or os.environ.get("MYSQLPORT", "3306")),
        "database": os.environ.get("DB_NAME") or os.environ.get("MYSQLDATABASE", "AgricultureDB"),
        "user": os.environ.get("DB_USER") or os.environ.get("MYSQLUSER", ""),
        "password": os.environ.get("DB_PASSWORD") or os.environ.get("MYSQLPASSWORD", "Jerrin@!1530"),
        "connection_timeout": 5,
    }


DB_CONFIG = get_database_config()


def init_database_if_needed() -> None:
    config = get_database_config()
    if not config.get("user"):
        return
    try:
        connection = mysql.connector.connect(**config)
        cursor = connection.cursor()
        cursor.execute("SHOW TABLES LIKE 'Users'")
        has_users = cursor.fetchone()
        if not has_users:
            print("Initializing database tables from schema.sql...", flush=True)
            schema_file = BACKEND_DIR / "schema.sql"
            if schema_file.exists():
                for stmt in schema_file.read_text(encoding="utf-8").split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        try:
                            cursor.execute(stmt)
                        except Exception:
                            pass
            connection.commit()

        # Check if master catalog data is missing
        cursor.execute("SHOW TABLES LIKE 'panchayaths'")
        if cursor.fetchone():
            cursor.execute("SELECT COUNT(*) FROM `panchayaths`")
            count = cursor.fetchone()[0]
            if count == 0:
                print("Panchayaths table is empty. Seeding master catalog...", flush=True)
                seed_file = BACKEND_DIR / "seed_catalog.sql"
                if seed_file.exists():
                    for stmt in seed_file.read_text(encoding="utf-8").split(";"):
                        stmt = stmt.strip()
                        if stmt:
                            try:
                                cursor.execute(stmt)
                            except Exception:
                                pass
                connection.commit()
                print("Master catalog successfully seeded!", flush=True)
        cursor.close()
        connection.close()
    except Exception as err:
        print(f"Database auto-init notice: {err}", file=sys.stderr)


init_database_if_needed()


class APIError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@contextmanager
def database_connection() -> Iterator[MySQLConnection]:
    config = get_database_config()
    if not config.get("user"):
        raise APIError(503, "Set DB_USER in backend/.env before using the API.")
    try:
        connection = mysql.connector.connect(**config)
    except mysql.connector.Error as error:
        print(f"MySQL connection failed: {error}", file=sys.stderr)
        raise APIError(503, "Database unavailable. Check the MySQL service and backend/.env.") from error

    try:
        yield connection
    finally:
        connection.close()


def encode_segment(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def issue_token(user_id: int) -> str:
    if len(APP_SECRET_KEY) < 32:
        raise APIError(503, "Set APP_SECRET_KEY to a random value of at least 32 characters.")
    header = encode_segment(b'{"alg":"HS256","typ":"JWT"}')
    payload = json.dumps(
        {"sub": user_id, "exp": int(time.time()) + TOKEN_LIFETIME_SECONDS},
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = encode_segment(payload)
    signing_input = f"{header}.{encoded}"
    signature = hmac.new(
        APP_SECRET_KEY.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{signing_input}.{encode_segment(signature)}"


def verify_token(token: str) -> int:
    if len(APP_SECRET_KEY) < 32:
        raise APIError(503, "Server authentication is not configured.")
    try:
        header, encoded, signature = token.split(".")
        header_data = json.loads(
            base64.urlsafe_b64decode(header + "=" * (-len(header) % 4))
        )
        if header_data != {"alg": "HS256", "typ": "JWT"}:
            raise ValueError("Unsupported token header")
        expected = encode_segment(
            hmac.new(
                APP_SECRET_KEY.encode("utf-8"),
                f"{header}.{encoded}".encode("ascii"),
                hashlib.sha256,
            ).digest()
        )
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid signature")
        payload = json.loads(
            base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        )
        user_id = payload["sub"]
        if not isinstance(user_id, int) or payload["exp"] <= int(time.time()):
            raise ValueError("Expired or malformed token")
        return user_id
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise APIError(401, "Invalid or expired login session.") from error


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${encode_segment(salt)}${encode_segment(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations, salt, expected = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        actual = encode_segment(
            hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                base64.urlsafe_b64decode(salt + "=" * (-len(salt) % 4)),
                int(iterations),
            )
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def parse_json_body(environ: dict[str, Any]) -> dict[str, Any]:
    try:
        content_length = int(environ.get("CONTENT_LENGTH") or "0")
    except ValueError as error:
        raise APIError(400, "Invalid Content-Length header.") from error
    if content_length > MAX_REQUEST_BYTES:
        raise APIError(413, "Request body is too large.")
    if content_length <= 0:
        raise APIError(400, "A JSON request body is required.")

    try:
        payload = json.loads(environ["wsgi.input"].read(content_length))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise APIError(400, "Request body must contain valid JSON.") from error
    if not isinstance(payload, dict):
        raise APIError(400, "Request body must be a JSON object.")
    return payload


def required_text(payload: dict[str, Any], key: str, label: str, limit: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise APIError(400, f"{label} is required.")
    value = value.strip()
    if len(value) > limit:
        raise APIError(400, f"{label} must be {limit} characters or fewer.")
    return value


def required_id(payload: dict[str, Any], key: str, label: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool):
        raise APIError(400, f"Select a valid {label}.")
    try:
        identifier = int(value)
    except (TypeError, ValueError) as error:
        raise APIError(400, f"Select a valid {label}.") from error
    if identifier <= 0:
        raise APIError(400, f"Select a valid {label}.")
    return identifier


def serialize_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": row["user_id"],
        "email": row["email"],
        "role": row["role"],
        "full_name": row.get("full_name"),
        "phone": row.get("phone"),
        "is_profile_complete": bool(row["is_profile_complete"]),
        "address": row.get("address"),
        "panchayath_id": row.get("panchayath_id"),
        "panchayath_name": row.get("panchayath_name"),
        "office_id": row.get("office_id"),
        "office_name": row.get("office_name"),
        "designation": row.get("designation"),
    }


def find_user(cursor: Any, user_id: int) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT u.user_id, u.email, u.role, u.full_name, u.phone,
               u.is_profile_complete,
               f.address,
               COALESCE(f.panchayath_id, o.panchayath_id) AS panchayath_id,
               COALESCE(p_farm.panchayath_name, p_off.panchayath_name) AS panchayath_name,
               o.office_id, ao.office_name, o.designation
        FROM Users AS u
        LEFT JOIN Farmers AS f ON f.user_id = u.user_id
        LEFT JOIN Panchayaths AS p_farm ON p_farm.panchayath_id = f.panchayath_id
        LEFT JOIN Officers AS o ON o.user_id = u.user_id
        LEFT JOIN Panchayaths AS p_off ON p_off.panchayath_id = o.panchayath_id
        LEFT JOIN Agriculture_Offices AS ao ON ao.office_id = o.office_id
        WHERE u.user_id = %s
        """,
        (user_id,),
    )
    return cursor.fetchone()


def authenticated_user(environ: dict[str, Any], required_role: str | None = None) -> dict[str, Any]:
    header = environ.get("HTTP_AUTHORIZATION", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise APIError(401, "Please log in to continue.")

    user_id = verify_token(token)
    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            row = find_user(cursor, user_id)
        finally:
            cursor.close()
    if not row:
        raise APIError(401, "Login session no longer belongs to an active account.")
    user = serialize_user(row)
    if required_role and user["role"] != required_role:
        raise APIError(403, "You do not have permission to access this resource.")
    return user


def handle_register(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    email = required_text(payload, "email", "Email", 150).lower()
    password = required_text(payload, "password", "Password", 256)
    role = (payload.get("role") or "").strip().upper()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise APIError(400, "Enter a valid email address.")
    if len(password) < 8:
        raise APIError(400, "Password must be at least 8 characters.")
    if role not in ("FARMER", "OFFICER"):
        raise APIError(400, "Role must be FARMER or OFFICER.")

    full_name = (payload.get("full_name") or "").strip() or None
    phone = (payload.get("phone") or "").strip() or None
    if phone and not re.fullmatch(r"[0-9+() .-]{7,15}", phone):
        raise APIError(400, "Enter a valid phone number.")

    is_complete = False
    officer_info: dict[str, Any] | None = None
    farmer_info: dict[str, Any] | None = None

    if role == "OFFICER":
        designation = (payload.get("designation") or "Agricultural Officer").strip()
        panchayath_id_raw = payload.get("panchayath_id")
        panchayath_id = int(panchayath_id_raw) if panchayath_id_raw and str(panchayath_id_raw).isdigit() and int(panchayath_id_raw) > 0 else None
        office_id_raw = payload.get("office_id")
        office_id = int(office_id_raw) if office_id_raw and str(office_id_raw).isdigit() and int(office_id_raw) > 0 else None

        if full_name and phone and (panchayath_id or office_id):
            is_complete = True
            officer_info = {
                "designation": designation,
                "panchayath_id": panchayath_id,
                "office_id": office_id,
            }
    elif role == "FARMER":
        address = (payload.get("address") or "").strip() or None
        panchayath_id_raw = payload.get("panchayath_id")
        panchayath_id = int(panchayath_id_raw) if panchayath_id_raw and str(panchayath_id_raw).isdigit() and int(panchayath_id_raw) > 0 else None
        if full_name and phone and address and panchayath_id:
            is_complete = True
            farmer_info = {
                "address": address,
                "panchayath_id": panchayath_id,
            }

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                INSERT INTO Users (email, password_hash, role, full_name, phone, is_profile_complete)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (email, hash_password(password), role, full_name, phone, is_complete),
            )
            user_id = cursor.lastrowid

            if role == "OFFICER" and officer_info:
                p_id = officer_info["panchayath_id"]
                off_id = officer_info["office_id"]
                if p_id and not off_id:
                    cursor.execute("SELECT office_id FROM Panchayaths WHERE panchayath_id = %s", (p_id,))
                    p_row = cursor.fetchone()
                    if p_row:
                        off_id = p_row["office_id"]

                cursor.execute(
                    """
                    INSERT INTO Officers (user_id, office_id, panchayath_id, designation)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (user_id, off_id, p_id, officer_info["designation"]),
                )
            elif role == "FARMER" and farmer_info:
                cursor.execute(
                    """
                    INSERT INTO Farmers (user_id, panchayath_id, address, registration_date)
                    VALUES (%s, %s, %s, CURDATE())
                    """,
                    (user_id, farmer_info["panchayath_id"], farmer_info["address"]),
                )
            connection.commit()
        except IntegrityError as error:
            connection.rollback()
            if error.errno == 1062:
                raise APIError(409, "An account with this email already exists.") from error
            raise
        finally:
            cursor.close()

    success_msg = (
        "Officer account registered in database successfully. Please log in."
        if (role == "OFFICER" and is_complete)
        else (
            "Farmer account registered in database successfully. Please log in."
            if (role == "FARMER" and is_complete)
            else "Account created. Please log in to complete your profile."
        )
    )
    return HTTPStatus.CREATED, {"message": success_msg}


def handle_login(payload: dict[str, Any]) -> dict[str, Any]:
    email = required_text(payload, "email", "Email", 150).lower()
    password = required_text(payload, "password", "Password", 256)
    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT user_id, password_hash FROM Users WHERE email = %s",
                (email,),
            )
            credentials = cursor.fetchone()
            if not credentials or not verify_password(password, credentials["password_hash"]):
                raise APIError(401, "Email or password is incorrect.")
            row = find_user(cursor, credentials["user_id"])
        finally:
            cursor.close()
    if not row:
        raise APIError(401, "Email or password is incorrect.")
    user = serialize_user(row)
    return {"token": issue_token(user["user_id"]), "user": user}


def handle_complete_profile(
    payload: dict[str, Any], user: dict[str, Any]
) -> dict[str, Any]:
    role = user["role"]
    full_name = required_text(payload, "full_name", "Full name", 100)
    phone = required_text(payload, "phone", "Phone", 15)
    if not re.fullmatch(r"[0-9+() .-]{7,15}", phone):
        raise APIError(400, "Enter a valid phone number.")

    if role == "FARMER":
        address = required_text(payload, "address", "Address", 255)
        panchayath_id = required_id(payload, "panchayath_id", "Gram Panchayath")
        office_id = None
    elif role == "OFFICER":
        designation = required_text(payload, "designation", "Designation", 100)
        panchayath_id_raw = payload.get("panchayath_id")
        panchayath_id = int(panchayath_id_raw) if panchayath_id_raw and str(panchayath_id_raw).isdigit() and int(panchayath_id_raw) > 0 else None
        office_id_raw = payload.get("office_id")
        office_id = int(office_id_raw) if office_id_raw and str(office_id_raw).isdigit() and int(office_id_raw) > 0 else None
        if not office_id and not panchayath_id:
            raise APIError(400, "Select an Agriculture Office or Gram Panchayath.")
    else:
        raise APIError(403, "This account role cannot complete a profile.")

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            current = find_user(cursor, user["user_id"])
            if not current:
                raise APIError(401, "Account not found.")
            if current["is_profile_complete"]:
                raise APIError(409, "This profile is already complete.")

            if role == "FARMER":
                cursor.execute(
                    "SELECT panchayath_id FROM Panchayaths WHERE panchayath_id = %s",
                    (panchayath_id,),
                )
                if not cursor.fetchone():
                    raise APIError(400, "Selected Gram Panchayath does not exist.")
            else:
                if panchayath_id:
                    cursor.execute(
                        "SELECT office_id FROM Panchayaths WHERE panchayath_id = %s",
                        (panchayath_id,),
                    )
                    p_row = cursor.fetchone()
                    if p_row:
                        office_id = p_row["office_id"]
                if office_id:
                    cursor.execute(
                        "SELECT office_id FROM Agriculture_Offices WHERE office_id = %s",
                        (office_id,),
                    )
                    if not cursor.fetchone():
                        raise APIError(400, "Selected Agriculture Office does not exist.")

            cursor.execute(
                """
                UPDATE Users
                SET full_name = %s, phone = %s, is_profile_complete = TRUE
                WHERE user_id = %s AND is_profile_complete = FALSE
                """,
                (full_name, phone, user["user_id"]),
            )
            if cursor.rowcount != 1:
                raise APIError(409, "This profile has already been completed.")

            if role == "FARMER":
                cursor.execute(
                    """
                    INSERT INTO Farmers (user_id, panchayath_id, address)
                    VALUES (%s, %s, %s)
                    """,
                    (user["user_id"], panchayath_id, address),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO Officers (user_id, office_id, panchayath_id, designation)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (user["user_id"], office_id, panchayath_id, designation),
                )
            connection.commit()
            updated = find_user(cursor, user["user_id"])
            if not updated:
                raise APIError(500, "Could not read the completed profile.")
            return {"user": serialize_user(updated)}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()


def handle_update_profile(
    payload: dict[str, Any], user: dict[str, Any]
) -> dict[str, Any]:
    role = user["role"]
    full_name = required_text(payload, "full_name", "Full name", 100)
    phone = required_text(payload, "phone", "Phone", 15)
    if not re.fullmatch(r"[0-9+() .-]{7,15}", phone):
        raise APIError(400, "Enter a valid phone number.")

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                "UPDATE Users SET full_name = %s, phone = %s WHERE user_id = %s",
                (full_name, phone, user["user_id"]),
            )
            if role == "FARMER":
                address = required_text(payload, "address", "Address", 255)
                panchayath_id = required_id(payload, "panchayath_id", "Gram Panchayath")
                cursor.execute(
                    "UPDATE Farmers SET address = %s, panchayath_id = %s WHERE user_id = %s",
                    (address, panchayath_id, user["user_id"]),
                )
            elif role == "OFFICER":
                designation = required_text(payload, "designation", "Designation", 100)
                panchayath_id_raw = payload.get("panchayath_id")
                panchayath_id = int(panchayath_id_raw) if panchayath_id_raw and str(panchayath_id_raw).isdigit() and int(panchayath_id_raw) > 0 else None
                office_id_raw = payload.get("office_id")
                office_id = int(office_id_raw) if office_id_raw and str(office_id_raw).isdigit() and int(office_id_raw) > 0 else None

                if panchayath_id and not office_id:
                    cursor.execute("SELECT office_id FROM Panchayaths WHERE panchayath_id = %s", (panchayath_id,))
                    p_row = cursor.fetchone()
                    if p_row:
                        office_id = p_row["office_id"]
                if not office_id:
                    office_id = required_id(payload, "office_id", "Agriculture Office")

                cursor.execute(
                    "UPDATE Officers SET designation = %s, office_id = %s, panchayath_id = %s WHERE user_id = %s",
                    (designation, office_id, panchayath_id, user["user_id"]),
                )
            connection.commit()
            updated = find_user(cursor, user["user_id"])
            if not updated:
                raise APIError(500, "Could not fetch updated user profile.")
            return {"message": "Profile updated successfully.", "user": serialize_user(updated)}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()


def seed_catalog_data(connection) -> None:
    cursor = connection.cursor()
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
    cursor.execute("SHOW TABLES")
    existing_tables = {row[0].lower(): row[0] for row in cursor.fetchall()}

    def tbl(name: str) -> str:
        return existing_tables.get(name.lower(), name)

    offices_tbl = tbl("Agriculture_Offices")
    panchayaths_tbl = tbl("Panchayaths")
    crops_tbl = tbl("Crops")
    fertilizers_tbl = tbl("Fertilizers")
    labour_tbl = tbl("Labour_Types")
    rental_tbl = tbl("Rental_Types")
    energy_tbl = tbl("Energy_Types")
    subsidies_tbl = tbl("Subsidies")

    cursor.execute(
        f"REPLACE INTO `{offices_tbl}` (office_id, office_name, phone, email, address) VALUES "
        "(1, 'Krishi Bhavan - Palakkad Central', '0491-2501234', 'kb.palakkad@agri.gov.in', 'Civil Station Complex, Palakkad'), "
        "(2, 'Krishi Bhavan - Alathur', '0492-2223456', 'kb.alathur@agri.gov.in', 'Main Road, Alathur, Palakkad'), "
        "(3, 'Krishi Bhavan - Chittur', '0492-3256789', 'kb.chittur@agri.gov.in', 'Taluk Office Road, Chittur'), "
        "(4, 'Krishi Bhavan - Thrissur Central', '0487-2334455', 'kb.thrissur@agri.gov.in', 'Ayyanthole, Thrissur')"
    )

    cursor.execute(
        f"REPLACE INTO `{panchayaths_tbl}` (panchayath_id, panchayath_name, district, office_id) VALUES "
        "(1, 'Pirayiri Gram Panchayath', 'Palakkad', 1), "
        "(2, 'Marutharode Gram Panchayath', 'Palakkad', 1), "
        "(3, 'Kannadi Gram Panchayath', 'Palakkad', 1), "
        "(4, 'Alathur Gram Panchayath', 'Palakkad', 2), "
        "(5, 'Kuzhalmannam Gram Panchayath', 'Palakkad', 2), "
        "(6, 'Kavassery Gram Panchayath', 'Palakkad', 2), "
        "(7, 'Vadakkencherry Gram Panchayath', 'Palakkad', 2), "
        "(8, 'Chittur-Thathamangalam', 'Palakkad', 3), "
        "(9, 'Pattanchery Gram Panchayath', 'Palakkad', 3), "
        "(10, 'Perumatty Gram Panchayath', 'Palakkad', 3), "
        "(11, 'Ollur Gram Panchayath', 'Thrissur', 4), "
        "(12, 'Nadathara Gram Panchayath', 'Thrissur', 4), "
        "(13, 'Puzhakkal Gram Panchayath', 'Thrissur', 4)"
    )

    cursor.execute(
        f"REPLACE INTO `{crops_tbl}` (crop_id, crop_name, crop_category, season, growth_duration_days, expected_yield_per_acre) VALUES "
        "(1, 'Rice', 'Cereal', 'Kharif', 120, 2200.00), "
        "(2, 'Wheat', 'Cereal', 'Rabi', 120, 1800.00)"
    )

    cursor.execute(
        f"REPLACE INTO `{fertilizers_tbl}` (fertilizer_id, fertilizer_name, fertilizer_type, unit) VALUES "
        "(1, 'Urea (46% N)', 'Chemical', 'kg'), "
        "(2, 'Factamfos (20:20:0:13)', 'Complex Chemical', 'kg'), "
        "(3, 'Muriate of Potash (MOP)', 'Chemical', 'kg'), "
        "(4, 'DAP (18:46:0)', 'Chemical', 'kg'), "
        "(5, 'Neem Cake Organic Fertilizer', 'Organic', 'kg'), "
        "(6, 'Vermicompost', 'Organic', 'kg')"
    )

    cursor.execute(
        f"REPLACE INTO `{labour_tbl}` (labour_id, labour_name, standard_daily_rate) VALUES "
        "(1, 'Land Preparation & Ploughing', 950.00), "
        "(2, 'Transplanting & Sowing', 850.00), "
        "(3, 'Weeding & Intercultivation', 800.00), "
        "(4, 'Fertilizer & Pesticide Application', 900.00), "
        "(5, 'Harvesting & Threshing', 950.00)"
    )

    cursor.execute(
        f"REPLACE INTO `{rental_tbl}` (rental_id, rental_name, description) VALUES "
        "(1, 'Tractor (45 HP) with Cultivator', 'Heavy mechanized land tillage equipment'), "
        "(2, 'Power Tiller', 'Two-wheel tillage machine suitable for paddy wet fields'), "
        "(3, 'Combined Harvester', 'Tracked paddy harvesting and threshing machine'), "
        "(4, 'Diesel Irrigation Pump Set (5 HP)', 'Centrifugal high flow water pump')"
    )

    cursor.execute(
        f"REPLACE INTO `{energy_tbl}` (energy_id, energy_name) VALUES "
        "(1, 'Agricultural Grid Electricity'), "
        "(2, 'Diesel for Pump/Tractor'), "
        "(3, 'Solar Water Pump Power')"
    )

    cursor.execute(
        f"REPLACE INTO `{subsidies_tbl}` (subsidy_id, subsidy_name, description, amount, start_date, end_date, eligibility_criteria) VALUES "
        "(1, 'Subhiksha Keralam Paddy Assistance', 'Direct financial aid per acre for active paddy cultivation.', 5500.00, '2026-01-01', '2026-12-31', 'Paddy farmers with registered land in Kerala'), "
        "(2, 'Organic Farming Incentive Scheme', 'Subsidy for adopting organic inputs and vermicomposting.', 8000.00, '2026-04-01', '2027-03-31', 'Certified organic or transitioning crop producers'), "
        "(3, 'Farm Mechanization Equipment Grant', '50% grant on hiring or procuring approved agricultural machinery.', 15000.00, '2026-01-01', '2026-12-31', 'Small and marginal farmers holding up to 5 acres'), "
        "(4, 'Micro-Irrigation Drip System Grant', 'Assistance for installation of drip and sprinkler irrigation.', 12000.00, '2026-02-01', '2026-11-30', 'Horticulture crop growers with dependable water source')"
    )

    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    connection.commit()
    cursor.close()
    print("Catalog seed data populated successfully!", flush=True)


def get_lookup_data(path: str) -> dict[str, Any]:
    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SHOW TABLES")
            existing_tables = {row[0].lower(): row[0] for row in cursor.fetchall()}

            if path == "/api/panchayaths":
                tbl_name = existing_tables.get("panchayaths", "Panchayaths")
                query = f"SELECT panchayath_id, panchayath_name, district, office_id FROM `{tbl_name}` ORDER BY panchayath_name"
                key = "panchayaths"
            else:
                tbl_name = existing_tables.get("agriculture_offices", "Agriculture_Offices")
                query = f"SELECT office_id, office_name FROM `{tbl_name}` ORDER BY office_name"
                key = "offices"

            cursor.execute(query)
            rows = cursor.fetchall()
            if not rows:
                print(f"{key} is empty! Auto-seeding catalog...", flush=True)
                seed_catalog_data(connection)
                cursor.execute(query)
                rows = cursor.fetchall()

            return {key: rows}
        finally:
            cursor.close()


def get_officer_farmers(user: dict[str, Any], query_string: str) -> dict[str, Any]:
    parsed = parse_qs(query_string)
    panchayath_id: int | None = None
    if parsed.get("panchayath_id"):
        try:
            val = int(parsed["panchayath_id"][0])
            if val > 0:
                panchayath_id = val
        except (ValueError, TypeError):
            pass

    office_param = parsed.get("office_id", [None])[0]

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT o.office_id, ao.office_name
                FROM Officers AS o
                JOIN Agriculture_Offices ao ON ao.office_id = o.office_id
                WHERE o.user_id = %s
                """,
                (user["user_id"],),
            )
            officer = cursor.fetchone()
            if not officer:
                raise APIError(403, "Complete your officer profile to view farmers.")

            where_clauses = ["1=1"]
            parameters: list[Any] = []

            if office_param == "all":
                pass
            elif office_param:
                try:
                    target_office = int(office_param)
                    where_clauses.append("p.office_id = %s")
                    parameters.append(target_office)
                except ValueError:
                    where_clauses.append("p.office_id = %s")
                    parameters.append(officer["office_id"])
            else:
                where_clauses.append("p.office_id = %s")
                parameters.append(officer["office_id"])

            if panchayath_id is not None:
                where_clauses.append("p.panchayath_id = %s")
                parameters.append(panchayath_id)

            where_sql = " AND ".join(where_clauses)

            cursor.execute(
                f"""
                SELECT f.farmer_id,
                       u.full_name AS farmer_name,
                       u.email AS farmer_email,
                       u.phone AS farmer_phone,
                       p.panchayath_id,
                       p.panchayath_name,
                       ao.office_id,
                       ao.office_name,
                       f.address AS farmer_address,
                       f.registration_date,
                       COALESCE(farm_stats.farms_count, 0) AS farms_count,
                       COALESCE(farm_stats.total_acres, 0) AS total_acres,
                       COALESCE(farm_stats.farms_summary, '') AS farms_summary,
                       COALESCE(crop_stats.crops_count, 0) AS crops_count,
                       COALESCE(crop_stats.crops_summary, '') AS crops_summary
                FROM Farmers f
                JOIN Users u ON u.user_id = f.user_id
                JOIN Panchayaths p ON p.panchayath_id = f.panchayath_id
                JOIN Agriculture_Offices ao ON ao.office_id = p.office_id
                LEFT JOIN (
                    SELECT farmer_id,
                           COUNT(farm_id) AS farms_count,
                           SUM(area_acres) AS total_acres,
                           GROUP_CONCAT(farm_name SEPARATOR ', ') AS farms_summary
                    FROM Farms
                    GROUP BY farmer_id
                ) farm_stats ON farm_stats.farmer_id = f.farmer_id
                LEFT JOIN (
                    SELECT f2.farmer_id,
                           COUNT(DISTINCT fc.farm_crop_id) AS crops_count,
                           GROUP_CONCAT(DISTINCT c.crop_name SEPARATOR ', ') AS crops_summary
                    FROM Farm_Crops fc
                    JOIN Farms f2 ON f2.farm_id = fc.farm_id
                    JOIN Crops c ON c.crop_id = fc.crop_id
                    GROUP BY f2.farmer_id
                ) crop_stats ON crop_stats.farmer_id = f.farmer_id
                WHERE {where_sql}
                ORDER BY p.panchayath_name, u.full_name
                """,
                tuple(parameters),
            )
            return {"farmers": cursor.fetchall()}
        finally:
            cursor.close()


def get_officer_records(user: dict[str, Any], query_string: str) -> dict[str, Any]:
    parsed = parse_qs(query_string)
    record_type = parsed.get("type", ["farms"])[0].lower()
    office_param = parsed.get("office_id", [None])[0]
    panchayath_id: int | None = None
    if parsed.get("panchayath_id"):
        try:
            val = int(parsed["panchayath_id"][0])
            if val > 0:
                panchayath_id = val
        except (ValueError, TypeError):
            pass

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT o.office_id, ao.office_name
                FROM Officers AS o
                JOIN Agriculture_Offices ao ON ao.office_id = o.office_id
                WHERE o.user_id = %s
                """,
                (user["user_id"],),
            )
            officer = cursor.fetchone()
            if not officer:
                raise APIError(403, "Complete your officer profile to view records.")

            where_clauses = ["1=1"]
            parameters: list[Any] = []

            if office_param == "all":
                pass
            elif office_param:
                try:
                    target_office = int(office_param)
                    where_clauses.append("p.office_id = %s")
                    parameters.append(target_office)
                except ValueError:
                    where_clauses.append("p.office_id = %s")
                    parameters.append(officer["office_id"])
            else:
                where_clauses.append("p.office_id = %s")
                parameters.append(officer["office_id"])

            if panchayath_id is not None:
                where_clauses.append("p.panchayath_id = %s")
                parameters.append(panchayath_id)

            where_sql = " AND ".join(where_clauses)

            if record_type == "farms":
                cursor.execute(
                    f"""
                    SELECT f.farm_id, f.farm_name, f.location, f.area_acres, f.soil_type, f.irrigation_type,
                           u.full_name AS farmer_name, u.phone AS farmer_phone, u.email AS farmer_email,
                           p.panchayath_name, ao.office_name
                    FROM Farms f
                    JOIN Farmers fm ON fm.farmer_id = f.farmer_id
                    JOIN Users u ON u.user_id = fm.user_id
                    JOIN Panchayaths p ON p.panchayath_id = fm.panchayath_id
                    JOIN Agriculture_Offices ao ON ao.office_id = p.office_id
                    WHERE {where_sql}
                    ORDER BY p.panchayath_name, u.full_name, f.farm_name
                    """,
                    tuple(parameters),
                )
                return {"records": cursor.fetchall()}

            elif record_type == "crops":
                cursor.execute(
                    f"""
                    SELECT fc.farm_crop_id, f.farm_name, c.crop_name, c.crop_category, fc.season,
                           fc.planting_date, fc.expected_harvest_date, fc.actual_harvest_date,
                           fc.cultivated_area_acres, fc.status,
                           u.full_name AS farmer_name, p.panchayath_name
                    FROM Farm_Crops fc
                    JOIN Farms f ON f.farm_id = fc.farm_id
                    JOIN Crops c ON c.crop_id = fc.crop_id
                    JOIN Farmers fm ON fm.farmer_id = f.farmer_id
                    JOIN Users u ON u.user_id = fm.user_id
                    JOIN Panchayaths p ON p.panchayath_id = fm.panchayath_id
                    WHERE {where_sql}
                    ORDER BY fc.planting_date DESC
                    """,
                    tuple(parameters),
                )
                return {"records": cursor.fetchall()}

            elif record_type == "expenses":
                cursor.execute(
                    f"""
                    SELECT e.expense_id, f.farm_name, c.crop_name, e.expense_category,
                           rt.rental_name, et.energy_name, e.amount, e.expense_date, e.description,
                           u.full_name AS farmer_name, p.panchayath_name
                    FROM Expenses e
                    JOIN Farms f ON f.farm_id = e.farm_id
                    JOIN Farmers fm ON fm.farmer_id = f.farmer_id
                    JOIN Users u ON u.user_id = fm.user_id
                    JOIN Panchayaths p ON p.panchayath_id = fm.panchayath_id
                    LEFT JOIN Farm_Crops fc ON fc.farm_crop_id = e.farm_crop_id
                    LEFT JOIN Crops c ON c.crop_id = fc.crop_id
                    LEFT JOIN Rental_Types rt ON rt.rental_id = e.rental_id
                    LEFT JOIN Energy_Types et ON et.energy_id = e.energy_id
                    WHERE {where_sql}
                    ORDER BY e.expense_date DESC
                    """,
                    tuple(parameters),
                )
                return {"records": cursor.fetchall()}

            elif record_type == "income":
                cursor.execute(
                    f"""
                    SELECT inc.income_id, f.farm_name, c.crop_name, inc.sale_date,
                           inc.quantity_sold, inc.unit, inc.price_per_unit, inc.total_income, inc.buyer_name,
                           u.full_name AS farmer_name, p.panchayath_name
                    FROM Income inc
                    JOIN Farm_Crops fc ON fc.farm_crop_id = inc.farm_crop_id
                    JOIN Farms f ON f.farm_id = fc.farm_id
                    JOIN Crops c ON c.crop_id = fc.crop_id
                    JOIN Farmers fm ON fm.farmer_id = f.farmer_id
                    JOIN Users u ON u.user_id = fm.user_id
                    JOIN Panchayaths p ON p.panchayath_id = fm.panchayath_id
                    WHERE {where_sql}
                    ORDER BY inc.sale_date DESC
                    """,
                    tuple(parameters),
                )
                return {"records": cursor.fetchall()}

            elif record_type == "fertilizers":
                cursor.execute(
                    f"""
                    SELECT fcf.application_id, f.farm_name, c.crop_name, fert.fertilizer_name, fert.fertilizer_type,
                           fcf.application_date, fcf.quantity, fert.unit, fcf.total_cost,
                           u.full_name AS farmer_name, p.panchayath_name
                    FROM Farm_Crop_Fertilizer fcf
                    JOIN Farm_Crops fc ON fc.farm_crop_id = fcf.farm_crop_id
                    JOIN Farms f ON f.farm_id = fc.farm_id
                    JOIN Crops c ON c.crop_id = fc.crop_id
                    JOIN Fertilizers fert ON fert.fertilizer_id = fcf.fertilizer_id
                    JOIN Farmers fm ON fm.farmer_id = f.farmer_id
                    JOIN Users u ON u.user_id = fm.user_id
                    JOIN Panchayaths p ON p.panchayath_id = fm.panchayath_id
                    WHERE {where_sql}
                    ORDER BY fcf.application_date DESC
                    """,
                    tuple(parameters),
                )
                return {"records": cursor.fetchall()}

            elif record_type == "labour":
                cursor.execute(
                    f"""
                    SELECT fcl.labour_usage_id, f.farm_name, c.crop_name, lt.labour_name,
                           fcl.work_date, fcl.worker_count, fcl.days_worked, fcl.total_cost,
                           u.full_name AS farmer_name, p.panchayath_name
                    FROM Farm_Crop_Labour fcl
                    JOIN Farm_Crops fc ON fc.farm_crop_id = fcl.farm_crop_id
                    JOIN Farms f ON f.farm_id = fc.farm_id
                    JOIN Crops c ON c.crop_id = fc.crop_id
                    JOIN Labour_Types lt ON lt.labour_id = fcl.labour_id
                    JOIN Farmers fm ON fm.farmer_id = f.farmer_id
                    JOIN Users u ON u.user_id = fm.user_id
                    JOIN Panchayaths p ON p.panchayath_id = fm.panchayath_id
                    WHERE {where_sql}
                    ORDER BY fcl.work_date DESC
                    """,
                    tuple(parameters),
                )
                return {"records": cursor.fetchall()}

            else:
                raise APIError(400, "Invalid record type.")
        finally:
            cursor.close()


def get_officer_farmer_details(farmer_id: int) -> dict[str, Any]:
    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT f.farmer_id, u.full_name AS farmer_name, u.email AS farmer_email, u.phone AS farmer_phone,
                       p.panchayath_name, ao.office_name, f.address AS farmer_address, f.registration_date
                FROM Farmers f
                JOIN Users u ON u.user_id = f.user_id
                JOIN Panchayaths p ON p.panchayath_id = f.panchayath_id
                JOIN Agriculture_Offices ao ON ao.office_id = p.office_id
                WHERE f.farmer_id = %s
                """,
                (farmer_id,),
            )
            farmer = cursor.fetchone()
            if not farmer:
                raise APIError(404, "Farmer not found.")

            cursor.execute(
                """
                SELECT farm_id, farm_name, location, area_acres, soil_type, irrigation_type
                FROM Farms WHERE farmer_id = %s ORDER BY farm_name
                """,
                (farmer_id,),
            )
            farms = cursor.fetchall()

            cursor.execute(
                """
                SELECT fc.farm_crop_id, f.farm_name, c.crop_name, c.crop_category,
                       fc.season, fc.planting_date, fc.expected_harvest_date, fc.cultivated_area_acres, fc.status
                FROM Farm_Crops fc
                JOIN Farms f ON f.farm_id = fc.farm_id
                JOIN Crops c ON c.crop_id = fc.crop_id
                WHERE f.farmer_id = %s
                ORDER BY fc.planting_date DESC
                """,
                (farmer_id,),
            )
            crops = cursor.fetchall()

            cursor.execute(
                """
                SELECT e.expense_id, f.farm_name, c.crop_name, e.expense_category,
                       rt.rental_name, et.energy_name, e.amount, e.expense_date, e.description
                FROM Expenses e
                JOIN Farms f ON f.farm_id = e.farm_id
                LEFT JOIN Farm_Crops fc ON fc.farm_crop_id = e.farm_crop_id
                LEFT JOIN Crops c ON c.crop_id = fc.crop_id
                LEFT JOIN Rental_Types rt ON rt.rental_id = e.rental_id
                LEFT JOIN Energy_Types et ON et.energy_id = e.energy_id
                WHERE f.farmer_id = %s
                ORDER BY e.expense_date DESC
                """,
                (farmer_id,),
            )
            expenses = cursor.fetchall()

            cursor.execute(
                """
                SELECT inc.income_id, f.farm_name, c.crop_name, inc.sale_date,
                       inc.quantity_sold, inc.unit, inc.price_per_unit, inc.total_income, inc.buyer_name
                FROM Income inc
                JOIN Farm_Crops fc ON fc.farm_crop_id = inc.farm_crop_id
                JOIN Farms f ON f.farm_id = fc.farm_id
                JOIN Crops c ON c.crop_id = fc.crop_id
                WHERE f.farmer_id = %s
                ORDER BY inc.sale_date DESC
                """,
                (farmer_id,),
            )
            income = cursor.fetchall()

            cursor.execute(
                """
                SELECT fcf.application_id, f.farm_name, c.crop_name, fert.fertilizer_name,
                       fcf.application_date, fcf.quantity, fert.unit, fcf.total_cost
                FROM Farm_Crop_Fertilizer fcf
                JOIN Farm_Crops fc ON fc.farm_crop_id = fcf.farm_crop_id
                JOIN Farms f ON f.farm_id = fc.farm_id
                JOIN Crops c ON c.crop_id = fc.crop_id
                JOIN Fertilizers fert ON fert.fertilizer_id = fcf.fertilizer_id
                WHERE f.farmer_id = %s
                ORDER BY fcf.application_date DESC
                """,
                (farmer_id,),
            )
            fertilizers = cursor.fetchall()

            cursor.execute(
                """
                SELECT fcl.labour_usage_id, f.farm_name, c.crop_name, lt.labour_name,
                       fcl.work_date, fcl.worker_count, fcl.days_worked, fcl.total_cost
                FROM Farm_Crop_Labour fcl
                JOIN Farm_Crops fc ON fc.farm_crop_id = fcl.farm_crop_id
                JOIN Farms f ON f.farm_id = fc.farm_id
                JOIN Crops c ON c.crop_id = fc.crop_id
                JOIN Labour_Types lt ON lt.labour_id = fcl.labour_id
                WHERE f.farmer_id = %s
                ORDER BY fcl.work_date DESC
                """,
                (farmer_id,),
            )
            labour = cursor.fetchall()

            cursor.execute(
                """
                SELECT fs.farmer_subsidy_id, s.subsidy_name, s.amount, fs.status,
                       fs.application_date, fs.approved_amount, fs.remarks
                FROM Farmer_Subsidies fs
                JOIN Subsidies s ON s.subsidy_id = fs.subsidy_id
                WHERE fs.farmer_id = %s
                ORDER BY fs.application_date DESC
                """,
                (farmer_id,),
            )
            subsidies = cursor.fetchall()

            return {
                "farmer": farmer,
                "farms": farms,
                "crops": crops,
                "expenses": expenses,
                "income": income,
                "fertilizers": fertilizers,
                "labour": labour,
                "subsidies": subsidies,
            }
        finally:
            cursor.close()


def get_reference_data() -> dict[str, Any]:
    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT crop_id, crop_name, crop_category, season, growth_duration_days, expected_yield_per_acre FROM Crops ORDER BY crop_name")
            crops = cursor.fetchall()
            cursor.execute("SELECT fertilizer_id, fertilizer_name, fertilizer_type, unit FROM Fertilizers ORDER BY fertilizer_name")
            fertilizers = cursor.fetchall()
            cursor.execute("SELECT labour_id, labour_name, standard_daily_rate FROM Labour_Types ORDER BY labour_name")
            labour_types = cursor.fetchall()
            cursor.execute("SELECT energy_id, energy_name FROM Energy_Types ORDER BY energy_name")
            energy_types = cursor.fetchall()
            cursor.execute("SELECT rental_id, rental_name, description FROM Rental_Types ORDER BY rental_name")
            rental_types = cursor.fetchall()
            cursor.execute("SELECT subsidy_id, subsidy_name, description, amount, start_date, end_date, eligibility_criteria FROM Subsidies ORDER BY subsidy_name")
            subsidies = cursor.fetchall()
            cursor.execute("SELECT panchayath_id, panchayath_name, district, office_id FROM Panchayaths ORDER BY panchayath_name")
            panchayaths = cursor.fetchall()
            cursor.execute("SELECT office_id, office_name FROM Agriculture_Offices ORDER BY office_name")
            offices = cursor.fetchall()
            return {
                "crops": crops,
                "fertilizers": fertilizers,
                "labour_types": labour_types,
                "energy_types": energy_types,
                "rental_types": rental_types,
                "subsidies": subsidies,
                "panchayaths": panchayaths,
                "offices": offices,
            }
        finally:
            cursor.close()


def get_farmer_id(cursor: Any, user_id: int) -> int:
    cursor.execute("SELECT farmer_id FROM Farmers WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    if not row:
        raise APIError(403, "Complete your farmer profile before performing farm operations.")
    return row["farmer_id"] if isinstance(row, dict) else row[0]


def get_farmer_overview(user: dict[str, Any]) -> dict[str, Any]:
    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            farmer_id = get_farmer_id(cursor, user["user_id"])

            cursor.execute(
                """
                SELECT f.farm_id, f.farm_name, f.location, f.area_acres,
                       f.soil_type, f.irrigation_type
                FROM Farms AS f
                WHERE f.farmer_id = %s
                ORDER BY f.farm_name, f.farm_id
                """,
                (farmer_id,),
            )
            farms = cursor.fetchall()

            cursor.execute(
                """
                SELECT fc.farm_crop_id, fc.farm_id, f.farm_name, fc.crop_id, c.crop_name,
                       c.crop_category, fc.season, fc.planting_date, fc.expected_harvest_date,
                       fc.actual_harvest_date, fc.cultivated_area_acres, fc.status
                FROM Farm_Crops AS fc
                JOIN Farms AS f ON f.farm_id = fc.farm_id
                JOIN Crops AS c ON c.crop_id = fc.crop_id
                WHERE f.farmer_id = %s
                ORDER BY fc.planting_date DESC, fc.farm_crop_id DESC
                """,
                (farmer_id,),
            )
            crops = cursor.fetchall()

            cursor.execute(
                """
                SELECT e.expense_id, e.farm_id, f.farm_name, e.farm_crop_id, c.crop_name,
                       e.expense_category, e.rental_id, rt.rental_name, e.energy_id, et.energy_name,
                       e.amount, e.expense_date, e.description
                FROM Expenses AS e
                JOIN Farms AS f ON f.farm_id = e.farm_id
                LEFT JOIN Farm_Crops AS fc ON fc.farm_crop_id = e.farm_crop_id
                LEFT JOIN Crops AS c ON c.crop_id = fc.crop_id
                LEFT JOIN Rental_Types AS rt ON rt.rental_id = e.rental_id
                LEFT JOIN Energy_Types AS et ON et.energy_id = e.energy_id
                WHERE f.farmer_id = %s
                ORDER BY e.expense_date DESC, e.expense_id DESC
                """,
                (farmer_id,),
            )
            expenses = cursor.fetchall()

            cursor.execute(
                """
                SELECT inc.income_id, inc.farm_crop_id, f.farm_name, c.crop_name,
                       inc.sale_date, inc.quantity_sold, inc.unit, inc.price_per_unit,
                       inc.total_income, inc.buyer_name
                FROM Income AS inc
                JOIN Farm_Crops AS fc ON fc.farm_crop_id = inc.farm_crop_id
                JOIN Farms AS f ON f.farm_id = fc.farm_id
                JOIN Crops AS c ON c.crop_id = fc.crop_id
                WHERE f.farmer_id = %s
                ORDER BY inc.sale_date DESC, inc.income_id DESC
                """,
                (farmer_id,),
            )
            income = cursor.fetchall()

            cursor.execute(
                """
                SELECT fcf.application_id, fcf.farm_crop_id, f.farm_name, c.crop_name,
                       fcf.fertilizer_id, fert.fertilizer_name, fert.fertilizer_type, fert.unit,
                       fcf.application_date, fcf.quantity, fcf.total_cost
                FROM Farm_Crop_Fertilizer AS fcf
                JOIN Farm_Crops AS fc ON fc.farm_crop_id = fcf.farm_crop_id
                JOIN Farms AS f ON f.farm_id = fc.farm_id
                JOIN Crops AS c ON c.crop_id = fc.crop_id
                JOIN Fertilizers AS fert ON fert.fertilizer_id = fcf.fertilizer_id
                WHERE f.farmer_id = %s
                ORDER BY fcf.application_date DESC, fcf.application_id DESC
                """,
                (farmer_id,),
            )
            fertilizers = cursor.fetchall()

            cursor.execute(
                """
                SELECT fcl.labour_usage_id, fcl.farm_crop_id, f.farm_name, c.crop_name,
                       fcl.labour_id, lt.labour_name, fcl.work_date, fcl.worker_count,
                       fcl.days_worked, fcl.total_cost
                FROM Farm_Crop_Labour AS fcl
                JOIN Farm_Crops AS fc ON fc.farm_crop_id = fcl.farm_crop_id
                JOIN Farms AS f ON f.farm_id = fc.farm_id
                JOIN Crops AS c ON c.crop_id = fc.crop_id
                JOIN Labour_Types AS lt ON lt.labour_id = fcl.labour_id
                WHERE f.farmer_id = %s
                ORDER BY fcl.work_date DESC, fcl.labour_usage_id DESC
                """,
                (farmer_id,),
            )
            labour = cursor.fetchall()

            cursor.execute(
                """
                SELECT fs.farmer_subsidy_id, s.subsidy_id, s.subsidy_name, s.description,
                       s.amount, fs.status, fs.application_date, fs.approved_amount,
                       fs.payment_date, fs.remarks, off_u.full_name AS officer_name,
                       p.panchayath_name, o.designation AS officer_designation
                FROM Farmer_Subsidies AS fs
                JOIN Subsidies AS s ON s.subsidy_id = fs.subsidy_id
                JOIN Farmers AS f ON f.farmer_id = fs.farmer_id
                JOIN Panchayaths AS p ON p.panchayath_id = f.panchayath_id
                LEFT JOIN Officers AS o ON o.officer_id = fs.officer_id
                LEFT JOIN Users AS off_u ON off_u.user_id = o.user_id
                WHERE fs.farmer_id = %s
                ORDER BY fs.application_date DESC, fs.farmer_subsidy_id DESC
                """,
                (farmer_id,),
            )
            subsidies = cursor.fetchall()

            total_expenses = sum(float(e["amount"] or 0) for e in expenses)
            total_fert_cost = sum(float(f["total_cost"] or 0) for f in fertilizers)
            total_labour_cost = sum(float(l["total_cost"] or 0) for l in labour)
            total_income = sum(float(i["total_income"] or 0) for i in income)
            total_subsidies = sum(float(s["approved_amount"] or 0) for s in subsidies if s["status"] in ("APPROVED", "PAID"))
            overall_cost = total_expenses + total_fert_cost + total_labour_cost
            net_balance = (total_income + total_subsidies) - overall_cost

            return {
                "farms": farms,
                "crops": crops,
                "expenses": expenses,
                "income": income,
                "fertilizers": fertilizers,
                "labour": labour,
                "subsidies": subsidies,
                "stats": {
                    "total_farms": len(farms),
                    "total_crops": len(crops),
                    "total_expenses": overall_cost,
                    "general_expenses": total_expenses,
                    "fertilizer_cost": total_fert_cost,
                    "labour_cost": total_labour_cost,
                    "total_income": total_income,
                    "approved_subsidies": total_subsidies,
                    "net_balance": net_balance,
                },
            }
        finally:
            cursor.close()


def handle_add_farm(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    farm_name = required_text(payload, "farm_name", "Farm name", 100)
    location = required_text(payload, "location", "Location", 255)
    try:
        area_acres = float(payload.get("area_acres") or 0.0)
    except (TypeError, ValueError):
        raise APIError(400, "Enter a valid area in acres.")
    if area_acres <= 0:
        raise APIError(400, "Area must be greater than 0 acres.")
    soil_type = (payload.get("soil_type") or "Clay Loam").strip()
    irrigation_type = (payload.get("irrigation_type") or "Canal / Borewell").strip()

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            farmer_id = get_farmer_id(cursor, user["user_id"])
            cursor.execute(
                """
                INSERT INTO Farms (farmer_id, farm_name, location, area_acres, soil_type, irrigation_type)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (farmer_id, farm_name, location, area_acres, soil_type, irrigation_type),
            )
            connection.commit()
            return {"message": "Farm registered successfully.", "farm_id": cursor.lastrowid}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()


def handle_plant_crop(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    farm_id = required_id(payload, "farm_id", "Farm")
    crop_id = required_id(payload, "crop_id", "Crop")
    season = (payload.get("season") or "Mundakan").strip()
    planting_date = required_text(payload, "planting_date", "Planting date", 20)
    expected_harvest_date = payload.get("expected_harvest_date") or None
    try:
        area_acres = float(payload.get("cultivated_area_acres") or 1.0)
    except (TypeError, ValueError):
        raise APIError(400, "Enter valid cultivated area in acres.")
    status = payload.get("status") or "GROWING"
    if status not in ("PLANNED", "GROWING", "HARVESTED", "FAILED"):
        status = "GROWING"

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            farmer_id = get_farmer_id(cursor, user["user_id"])
            cursor.execute("SELECT farm_id FROM Farms WHERE farm_id = %s AND farmer_id = %s", (farm_id, farmer_id))
            if not cursor.fetchone():
                raise APIError(403, "Selected farm does not belong to you.")

            cursor.execute("SELECT crop_id, crop_name FROM Crops WHERE crop_id = %s", (crop_id,))
            crop_row = cursor.fetchone()
            if not crop_row or crop_row["crop_name"].lower() not in ("rice", "wheat"):
                raise APIError(400, "Invalid crop. Only Rice and Wheat are permitted in this system.")

            cursor.execute(
                """
                INSERT INTO Farm_Crops (farm_id, crop_id, season, planting_date, expected_harvest_date, cultivated_area_acres, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (farm_id, crop_id, season, planting_date, expected_harvest_date, area_acres, status),
            )
            connection.commit()
            return {"message": "Crop cycle planted successfully.", "farm_crop_id": cursor.lastrowid}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()


def handle_add_expense(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    farm_id = required_id(payload, "farm_id", "Farm")
    farm_crop_id = payload.get("farm_crop_id") or None
    category = payload.get("expense_category") or "OTHER"
    if category not in ("SEEDS", "RENTAL", "ENERGY", "IRRIGATION", "TRANSPORT", "OTHER"):
        category = "OTHER"
    rental_id = payload.get("rental_id") or None
    energy_id = payload.get("energy_id") or None
    try:
        amount = float(payload.get("amount") or 0.0)
    except (TypeError, ValueError):
        raise APIError(400, "Enter a valid expense amount.")
    if amount <= 0:
        raise APIError(400, "Expense amount must be greater than zero.")
    expense_date = required_text(payload, "expense_date", "Expense date", 20)
    description = (payload.get("description") or "").strip()

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            farmer_id = get_farmer_id(cursor, user["user_id"])
            cursor.execute("SELECT farm_id FROM Farms WHERE farm_id = %s AND farmer_id = %s", (farm_id, farmer_id))
            if not cursor.fetchone():
                raise APIError(403, "Selected farm does not belong to you.")

            cursor.execute(
                """
                INSERT INTO Expenses (farm_id, farm_crop_id, expense_category, rental_id, energy_id, amount, expense_date, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (farm_id, farm_crop_id, category, rental_id, energy_id, amount, expense_date, description),
            )
            connection.commit()
            return {"message": "Expense recorded successfully.", "expense_id": cursor.lastrowid}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()


def handle_add_income(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    farm_crop_id = required_id(payload, "farm_crop_id", "Crop Cycle")
    sale_date = required_text(payload, "sale_date", "Sale date", 20)
    try:
        qty = float(payload.get("quantity_sold") or 0.0)
        price = float(payload.get("price_per_unit") or 0.0)
    except (TypeError, ValueError):
        raise APIError(400, "Enter valid quantity and price.")
    if qty <= 0 or price <= 0:
        raise APIError(400, "Quantity and price must be greater than zero.")

    total_income = float(payload.get("total_income") or (qty * price))
    unit = (payload.get("unit") or "kg").strip()
    buyer = (payload.get("buyer_name") or "Local Market").strip()

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            farmer_id = get_farmer_id(cursor, user["user_id"])
            cursor.execute(
                """
                SELECT fc.farm_crop_id
                FROM Farm_Crops fc
                JOIN Farms f ON f.farm_id = fc.farm_id
                WHERE fc.farm_crop_id = %s AND f.farmer_id = %s
                """,
                (farm_crop_id, farmer_id),
            )
            if not cursor.fetchone():
                raise APIError(403, "Crop cycle does not belong to your farms.")

            cursor.execute(
                """
                INSERT INTO Income (farm_crop_id, sale_date, quantity_sold, unit, price_per_unit, buyer_name)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (farm_crop_id, sale_date, qty, unit, price, buyer),
            )
            connection.commit()
            return {"message": "Harvest sales income recorded successfully.", "income_id": cursor.lastrowid}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()


def handle_add_fertilizer(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    farm_crop_id = required_id(payload, "farm_crop_id", "Crop Cycle")
    fertilizer_id = required_id(payload, "fertilizer_id", "Fertilizer")
    application_date = required_text(payload, "application_date", "Application date", 20)
    try:
        quantity = float(payload.get("quantity") or 0.0)
        total_cost = float(payload.get("total_cost") or 0.0)
    except (TypeError, ValueError):
        raise APIError(400, "Enter valid quantity and cost.")

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            farmer_id = get_farmer_id(cursor, user["user_id"])
            cursor.execute(
                """
                SELECT fc.farm_crop_id
                FROM Farm_Crops fc
                JOIN Farms f ON f.farm_id = fc.farm_id
                WHERE fc.farm_crop_id = %s AND f.farmer_id = %s
                """,
                (farm_crop_id, farmer_id),
            )
            if not cursor.fetchone():
                raise APIError(403, "Crop cycle does not belong to your farms.")

            cursor.execute(
                """
                INSERT INTO Farm_Crop_Fertilizer (farm_crop_id, fertilizer_id, application_date, quantity, total_cost)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (farm_crop_id, fertilizer_id, application_date, quantity, total_cost),
            )
            connection.commit()
            return {"message": "Fertilizer application logged.", "application_id": cursor.lastrowid}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()


def handle_add_labour(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    farm_crop_id = required_id(payload, "farm_crop_id", "Crop Cycle")
    labour_id = required_id(payload, "labour_id", "Labour Type")
    work_date = required_text(payload, "work_date", "Work date", 20)
    try:
        worker_count = int(payload.get("worker_count") or 1)
        days_worked = float(payload.get("days_worked") or 1.0)
        total_cost = float(payload.get("total_cost") or 0.0)
    except (TypeError, ValueError):
        raise APIError(400, "Enter valid worker count, days, and cost.")

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            farmer_id = get_farmer_id(cursor, user["user_id"])
            cursor.execute(
                """
                SELECT fc.farm_crop_id
                FROM Farm_Crops fc
                JOIN Farms f ON f.farm_id = fc.farm_id
                WHERE fc.farm_crop_id = %s AND f.farmer_id = %s
                """,
                (farm_crop_id, farmer_id),
            )
            if not cursor.fetchone():
                raise APIError(403, "Crop cycle does not belong to your farms.")

            cursor.execute(
                """
                INSERT INTO Farm_Crop_Labour (farm_crop_id, labour_id, work_date, worker_count, days_worked, total_cost)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (farm_crop_id, labour_id, work_date, worker_count, days_worked, total_cost),
            )
            connection.commit()
            return {"message": "Farm labour recorded successfully.", "labour_usage_id": cursor.lastrowid}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()


def handle_apply_subsidy(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    subsidy_id = required_id(payload, "subsidy_id", "Subsidy Scheme")
    application_date = (payload.get("application_date") or time.strftime("%Y-%m-%d")).strip()
    remarks = (payload.get("remarks") or "Application submitted online via portal.").strip()
    farm_id_raw = payload.get("farm_id")

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            farmer_id = get_farmer_id(cursor, user["user_id"])
            cursor.execute(
                """
                SELECT f.panchayath_id, p.panchayath_name, p.office_id, ao.office_name
                FROM Farmers f
                JOIN Panchayaths p ON p.panchayath_id = f.panchayath_id
                JOIN Agriculture_Offices ao ON ao.office_id = p.office_id
                WHERE f.farmer_id = %s
                LIMIT 1
                """,
                (farmer_id,),
            )
            farmer_p = cursor.fetchone()
            if not farmer_p:
                raise APIError(400, "Farmer profile not found. Please complete profile setup first.")

            # If a specific farm was selected, verify ownership and tag remarks
            if farm_id_raw:
                try:
                    farm_id = int(farm_id_raw)
                    cursor.execute(
                        "SELECT farm_name, location, area_acres FROM Farms WHERE farm_id = %s AND farmer_id = %s",
                        (farm_id, farmer_id),
                    )
                    farm_row = cursor.fetchone()
                    if farm_row:
                        farm_tag = f"[Farm: {farm_row['farm_name']} ({farm_row['location']}, {farm_row['area_acres']} acres)]"
                        if farm_tag not in remarks:
                            remarks = f"{farm_tag} {remarks}".strip()
                except (ValueError, TypeError):
                    pass

            # Route to the Agricultural Officer assigned to this Gram Panchayath, or fallback to Krishi Bhavan
            cursor.execute(
                "SELECT officer_id FROM Officers WHERE panchayath_id = %s LIMIT 1",
                (farmer_p["panchayath_id"],),
            )
            p_officer = cursor.fetchone()
            if p_officer:
                assigned_officer_id = p_officer["officer_id"]
            else:
                cursor.execute(
                    "SELECT officer_id FROM Officers WHERE office_id = %s LIMIT 1",
                    (farmer_p["office_id"],),
                )
                kb_officer = cursor.fetchone()
                assigned_officer_id = kb_officer["officer_id"] if kb_officer else None

            cursor.execute(
                """
                INSERT INTO Farmer_Subsidies (farmer_id, subsidy_id, officer_id, application_date, status, remarks)
                VALUES (%s, %s, %s, %s, 'PENDING', %s)
                ON DUPLICATE KEY UPDATE application_date = VALUES(application_date), remarks = VALUES(remarks), officer_id = VALUES(officer_id)
                """,
                (farmer_id, subsidy_id, assigned_officer_id, application_date, remarks),
            )
            connection.commit()
            p_name = farmer_p["panchayath_name"]
            ao_name = farmer_p["office_name"]
            return {"message": f"Subsidy application submitted to Agricultural Officer for {p_name} ({ao_name})."}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()


def get_officer_subsidies(user: dict[str, Any]) -> dict[str, Any]:
    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT o.officer_id, o.office_id, o.panchayath_id, p.panchayath_name, ao.office_name
                FROM Officers o
                LEFT JOIN Panchayaths p ON p.panchayath_id = o.panchayath_id
                LEFT JOIN Agriculture_Offices ao ON ao.office_id = o.office_id
                WHERE o.user_id = %s
                """,
                (user["user_id"],),
            )
            officer = cursor.fetchone()
            if not officer:
                raise APIError(403, "Complete your officer profile to view subsidies.")

            # Strict jurisdiction isolation:
            # If assigned to a specific Gram Panchayath, only return applications from that Gram Panchayath.
            # If assigned at the Krishi Bhavan level, only return applications from Gram Panchayaths under that Krishi Bhavan.
            if officer.get("panchayath_id"):
                where_sql = "f.panchayath_id = %s"
                filter_val = officer["panchayath_id"]
            else:
                where_sql = "p.office_id = %s"
                filter_val = officer["office_id"]

            cursor.execute(
                f"""
                SELECT fs.farmer_subsidy_id, fs.farmer_id, u.full_name AS farmer_name,
                       u.email AS farmer_email, u.phone AS farmer_phone,
                       p.panchayath_id, p.panchayath_name, ao.office_name,
                       s.subsidy_id, s.subsidy_name, s.amount,
                       fs.status, fs.application_date, fs.approved_amount, fs.remarks,
                       fs.officer_id
                FROM Farmer_Subsidies AS fs
                JOIN Farmers AS f ON f.farmer_id = fs.farmer_id
                JOIN Users AS u ON u.user_id = f.user_id
                JOIN Panchayaths AS p ON p.panchayath_id = f.panchayath_id
                JOIN Agriculture_Offices AS ao ON ao.office_id = p.office_id
                JOIN Subsidies AS s ON s.subsidy_id = fs.subsidy_id
                WHERE {where_sql}
                ORDER BY fs.application_date DESC, fs.farmer_subsidy_id DESC
                """,
                (filter_val,),
            )
            return {
                "subsidies": cursor.fetchall(),
                "officer_panchayath_id": officer.get("panchayath_id"),
                "officer_panchayath_name": officer.get("panchayath_name"),
                "officer_office_id": officer.get("office_id"),
                "officer_office_name": officer.get("office_name"),
            }
        finally:
            cursor.close()


def handle_review_subsidy(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    farmer_subsidy_id = required_id(payload, "farmer_subsidy_id", "Subsidy Application")
    status = payload.get("status") or "APPROVED"
    if status not in ("APPROVED", "REJECTED", "PAID"):
        status = "APPROVED"
    approved_amount = float(payload.get("approved_amount") or 0.0) if status == "APPROVED" else 0.0
    remarks = (payload.get("remarks") or f"Reviewed by Officer {user.get('full_name', '')}").strip()

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT o.officer_id, o.office_id, o.panchayath_id, p.panchayath_name, ao.office_name
                FROM Officers o
                LEFT JOIN Panchayaths p ON p.panchayath_id = o.panchayath_id
                LEFT JOIN Agriculture_Offices ao ON ao.office_id = o.office_id
                WHERE o.user_id = %s
                """,
                (user["user_id"],),
            )
            officer = cursor.fetchone()
            if not officer:
                raise APIError(403, "Officer account not authorized or profile incomplete.")

            # Validate that the subsidy application is in this officer's assigned Gram Panchayath or Krishi Bhavan
            cursor.execute(
                """
                SELECT fs.farmer_subsidy_id, f.panchayath_id, p.panchayath_name, p.office_id, ao.office_name,
                       u.full_name AS farmer_name
                FROM Farmer_Subsidies fs
                JOIN Farmers f ON f.farmer_id = fs.farmer_id
                JOIN Users u ON u.user_id = f.user_id
                JOIN Panchayaths p ON p.panchayath_id = f.panchayath_id
                JOIN Agriculture_Offices ao ON ao.office_id = p.office_id
                WHERE fs.farmer_subsidy_id = %s
                """,
                (farmer_subsidy_id,),
            )
            sub_row = cursor.fetchone()
            if not sub_row:
                raise APIError(404, "Subsidy application not found.")

            # Strict jurisdiction check:
            # 1. If officer is assigned to a specific Gram Panchayath:
            if officer.get("panchayath_id"):
                if officer["panchayath_id"] != sub_row["panchayath_id"]:
                    raise APIError(
                        403,
                        f"Jurisdiction Restriction: You are the Agricultural Officer for {officer.get('panchayath_name') or 'your Gram Panchayath'}. Subsidies for farmer '{sub_row['farmer_name']}' in {sub_row['panchayath_name']} can only be approved by the designated Agricultural Officer for {sub_row['panchayath_name']}."
                    )
            # 2. If officer is assigned at the Krishi Bhavan level:
            else:
                if officer["office_id"] != sub_row["office_id"]:
                    raise APIError(
                        403,
                        f"Jurisdiction Restriction: This farmer belongs to {sub_row['office_name']}. You can only review applications within {officer.get('office_name') or 'your Krishi Bhavan'} jurisdiction."
                    )

            payment_date = time.strftime("%Y-%m-%d") if status == "APPROVED" else None
            cursor.execute(
                """
                UPDATE Farmer_Subsidies AS fs
                SET fs.status = %s, fs.approved_amount = %s, fs.remarks = %s, fs.officer_id = %s, fs.payment_date = %s
                WHERE fs.farmer_subsidy_id = %s
                """,
                (status, approved_amount, remarks, officer["officer_id"], payment_date, farmer_subsidy_id),
            )
            connection.commit()
            if cursor.rowcount == 0:
                raise APIError(404, "Subsidy application not found.")
            return {"message": f"Subsidy application status updated to {status}."}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()


def handle_edit_farm(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    farm_id = required_id(payload, "farm_id", "Farm")
    farm_name = required_text(payload, "farm_name", "Farm name", 100)
    location = required_text(payload, "location", "Location", 255)
    try:
        area_acres = float(payload.get("area_acres") or 0.0)
    except (TypeError, ValueError):
        raise APIError(400, "Enter a valid area in acres.")
    if area_acres <= 0:
        raise APIError(400, "Area must be greater than 0 acres.")
    soil_type = (payload.get("soil_type") or "Clay Loam").strip()
    irrigation_type = (payload.get("irrigation_type") or "Canal / Borewell").strip()

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            farmer_id = get_farmer_id(cursor, user["user_id"])
            cursor.execute("SELECT farm_id FROM Farms WHERE farm_id = %s AND farmer_id = %s", (farm_id, farmer_id))
            if not cursor.fetchone():
                raise APIError(404, "Farm not found or you do not have permission to edit it.")

            cursor.execute(
                """
                UPDATE Farms
                SET farm_name = %s, location = %s, area_acres = %s, soil_type = %s, irrigation_type = %s
                WHERE farm_id = %s AND farmer_id = %s
                """,
                (farm_name, location, area_acres, soil_type, irrigation_type, farm_id, farmer_id),
            )
            connection.commit()
            return {"message": "Farm plot updated successfully."}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()


def handle_edit_crop(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    farm_crop_id = required_id(payload, "farm_crop_id", "Crop Cycle")
    farm_id = required_id(payload, "farm_id", "Farm")
    crop_id = required_id(payload, "crop_id", "Crop")
    season = (payload.get("season") or "Kharif").strip()
    planting_date = required_text(payload, "planting_date", "Planting date", 20)
    expected_harvest_date = payload.get("expected_harvest_date") or None
    actual_harvest_date = payload.get("actual_harvest_date") or None
    try:
        area_acres = float(payload.get("cultivated_area_acres") or 1.0)
    except (TypeError, ValueError):
        raise APIError(400, "Enter valid cultivated area in acres.")
    status = payload.get("status") or "GROWING"
    if status not in ("PLANNED", "GROWING", "HARVESTED", "FAILED"):
        status = "GROWING"

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            farmer_id = get_farmer_id(cursor, user["user_id"])
            cursor.execute("SELECT farm_id FROM Farms WHERE farm_id = %s AND farmer_id = %s", (farm_id, farmer_id))
            if not cursor.fetchone():
                raise APIError(403, "Selected farm does not belong to you.")

            cursor.execute(
                """
                SELECT fc.farm_crop_id
                FROM Farm_Crops fc
                JOIN Farms f ON f.farm_id = fc.farm_id
                WHERE fc.farm_crop_id = %s AND f.farmer_id = %s
                """,
                (farm_crop_id, farmer_id),
            )
            if not cursor.fetchone():
                raise APIError(404, "Crop cycle not found or you do not have permission to edit it.")

            cursor.execute("SELECT crop_id, crop_name FROM Crops WHERE crop_id = %s", (crop_id,))
            crop_row = cursor.fetchone()
            if not crop_row or crop_row["crop_name"].lower() not in ("rice", "wheat"):
                raise APIError(400, "Invalid crop. Only Rice and Wheat are permitted in this system.")

            cursor.execute(
                """
                UPDATE Farm_Crops fc
                JOIN Farms f ON f.farm_id = fc.farm_id
                SET fc.farm_id = %s, fc.crop_id = %s, fc.season = %s, fc.planting_date = %s,
                    fc.expected_harvest_date = %s, fc.actual_harvest_date = %s,
                    fc.cultivated_area_acres = %s, fc.status = %s
                WHERE fc.farm_crop_id = %s AND f.farmer_id = %s
                """,
                (farm_id, crop_id, season, planting_date, expected_harvest_date, actual_harvest_date, area_acres, status, farm_crop_id, farmer_id),
            )
            connection.commit()
            return {"message": "Crop cycle updated successfully."}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()


def handle_edit_expense(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    expense_id = required_id(payload, "expense_id", "Expense")
    farm_id = required_id(payload, "farm_id", "Farm")
    farm_crop_id = payload.get("farm_crop_id") or None
    category = payload.get("expense_category") or "OTHER"
    if category not in ("SEEDS", "RENTAL", "ENERGY", "IRRIGATION", "TRANSPORT", "OTHER"):
        category = "OTHER"
    rental_id = payload.get("rental_id") or None
    energy_id = payload.get("energy_id") or None
    try:
        amount = float(payload.get("amount") or 0.0)
    except (TypeError, ValueError):
        raise APIError(400, "Enter a valid expense amount.")
    if amount <= 0:
        raise APIError(400, "Expense amount must be greater than zero.")
    expense_date = required_text(payload, "expense_date", "Expense date", 20)
    description = (payload.get("description") or "").strip()

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            farmer_id = get_farmer_id(cursor, user["user_id"])
            cursor.execute("SELECT farm_id FROM Farms WHERE farm_id = %s AND farmer_id = %s", (farm_id, farmer_id))
            if not cursor.fetchone():
                raise APIError(403, "Selected farm does not belong to you.")

            cursor.execute(
                """
                SELECT e.expense_id
                FROM Expenses e
                JOIN Farms f ON f.farm_id = e.farm_id
                WHERE e.expense_id = %s AND f.farmer_id = %s
                """,
                (expense_id, farmer_id),
            )
            if not cursor.fetchone():
                raise APIError(404, "Expense record not found or unauthorized.")

            cursor.execute(
                """
                UPDATE Expenses e
                JOIN Farms f ON f.farm_id = e.farm_id
                SET e.farm_id = %s, e.farm_crop_id = %s, e.expense_category = %s,
                    e.rental_id = %s, e.energy_id = %s, e.amount = %s,
                    e.expense_date = %s, e.description = %s
                WHERE e.expense_id = %s AND f.farmer_id = %s
                """,
                (farm_id, farm_crop_id, category, rental_id, energy_id, amount, expense_date, description, expense_id, farmer_id),
            )
            connection.commit()
            return {"message": "Expense record updated successfully."}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()


def handle_edit_income(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    income_id = required_id(payload, "income_id", "Income")
    farm_crop_id = required_id(payload, "farm_crop_id", "Crop Cycle")
    sale_date = required_text(payload, "sale_date", "Sale date", 20)
    try:
        qty = float(payload.get("quantity_sold") or 0.0)
        price = float(payload.get("price_per_unit") or 0.0)
    except (TypeError, ValueError):
        raise APIError(400, "Enter valid quantity and price.")
    if qty <= 0 or price <= 0:
        raise APIError(400, "Quantity and price must be greater than zero.")
    unit = (payload.get("unit") or "kg").strip()
    buyer = (payload.get("buyer_name") or "Local Market").strip()

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            farmer_id = get_farmer_id(cursor, user["user_id"])
            cursor.execute(
                """
                SELECT fc.farm_crop_id
                FROM Farm_Crops fc
                JOIN Farms f ON f.farm_id = fc.farm_id
                WHERE fc.farm_crop_id = %s AND f.farmer_id = %s
                """,
                (farm_crop_id, farmer_id),
            )
            if not cursor.fetchone():
                raise APIError(403, "Crop cycle does not belong to your farms.")

            cursor.execute(
                """
                SELECT inc.income_id
                FROM Income inc
                JOIN Farm_Crops fc ON fc.farm_crop_id = inc.farm_crop_id
                JOIN Farms f ON f.farm_id = fc.farm_id
                WHERE inc.income_id = %s AND f.farmer_id = %s
                """,
                (income_id, farmer_id),
            )
            if not cursor.fetchone():
                raise APIError(404, "Income record not found or unauthorized.")

            cursor.execute(
                """
                UPDATE Income inc
                JOIN Farm_Crops fc ON fc.farm_crop_id = inc.farm_crop_id
                JOIN Farms f ON f.farm_id = fc.farm_id
                SET inc.farm_crop_id = %s, inc.sale_date = %s, inc.quantity_sold = %s,
                    inc.unit = %s, inc.price_per_unit = %s, inc.buyer_name = %s
                WHERE inc.income_id = %s AND f.farmer_id = %s
                """,
                (farm_crop_id, sale_date, qty, unit, price, buyer, income_id, farmer_id),
            )
            connection.commit()
            return {"message": "Harvest produce sale record updated successfully."}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()


def handle_edit_fertilizer(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    application_id = required_id(payload, "application_id", "Fertilizer Log")
    farm_crop_id = required_id(payload, "farm_crop_id", "Crop Cycle")
    fertilizer_id = required_id(payload, "fertilizer_id", "Fertilizer")
    application_date = required_text(payload, "application_date", "Application date", 20)
    try:
        quantity = float(payload.get("quantity") or 0.0)
        total_cost = float(payload.get("total_cost") or 0.0)
    except (TypeError, ValueError):
        raise APIError(400, "Enter valid quantity and cost.")

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            farmer_id = get_farmer_id(cursor, user["user_id"])
            cursor.execute(
                """
                SELECT fc.farm_crop_id
                FROM Farm_Crops fc
                JOIN Farms f ON f.farm_id = fc.farm_id
                WHERE fc.farm_crop_id = %s AND f.farmer_id = %s
                """,
                (farm_crop_id, farmer_id),
            )
            if not cursor.fetchone():
                raise APIError(403, "Crop cycle does not belong to your farms.")

            cursor.execute(
                """
                SELECT fcf.application_id
                FROM Farm_Crop_Fertilizer fcf
                JOIN Farm_Crops fc ON fc.farm_crop_id = fcf.farm_crop_id
                JOIN Farms f ON f.farm_id = fc.farm_id
                WHERE fcf.application_id = %s AND f.farmer_id = %s
                """,
                (application_id, farmer_id),
            )
            if not cursor.fetchone():
                raise APIError(404, "Fertilizer log not found or unauthorized.")

            cursor.execute(
                """
                UPDATE Farm_Crop_Fertilizer fcf
                JOIN Farm_Crops fc ON fc.farm_crop_id = fcf.farm_crop_id
                JOIN Farms f ON f.farm_id = fc.farm_id
                SET fcf.farm_crop_id = %s, fcf.fertilizer_id = %s,
                    fcf.application_date = %s, fcf.quantity = %s, fcf.total_cost = %s
                WHERE fcf.application_id = %s AND f.farmer_id = %s
                """,
                (farm_crop_id, fertilizer_id, application_date, quantity, total_cost, application_id, farmer_id),
            )
            connection.commit()
            return {"message": "Fertilizer application record updated successfully."}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()


def handle_edit_labour(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    labour_usage_id = required_id(payload, "labour_usage_id", "Labour Usage")
    farm_crop_id = required_id(payload, "farm_crop_id", "Crop Cycle")
    labour_id = required_id(payload, "labour_id", "Labour Type")
    work_date = required_text(payload, "work_date", "Work date", 20)
    try:
        worker_count = int(payload.get("worker_count") or 1)
        days_worked = float(payload.get("days_worked") or 1.0)
        total_cost = float(payload.get("total_cost") or 0.0)
    except (TypeError, ValueError):
        raise APIError(400, "Enter valid worker count, days, and cost.")

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            farmer_id = get_farmer_id(cursor, user["user_id"])
            cursor.execute(
                """
                SELECT fc.farm_crop_id
                FROM Farm_Crops fc
                JOIN Farms f ON f.farm_id = fc.farm_id
                WHERE fc.farm_crop_id = %s AND f.farmer_id = %s
                """,
                (farm_crop_id, farmer_id),
            )
            if not cursor.fetchone():
                raise APIError(403, "Crop cycle does not belong to your farms.")

            cursor.execute(
                """
                SELECT fcl.labour_usage_id
                FROM Farm_Crop_Labour fcl
                JOIN Farm_Crops fc ON fc.farm_crop_id = fcl.farm_crop_id
                JOIN Farms f ON f.farm_id = fc.farm_id
                WHERE fcl.labour_usage_id = %s AND f.farmer_id = %s
                """,
                (labour_usage_id, farmer_id),
            )
            if not cursor.fetchone():
                raise APIError(404, "Labour log not found or unauthorized.")

            cursor.execute(
                """
                UPDATE Farm_Crop_Labour fcl
                JOIN Farm_Crops fc ON fc.farm_crop_id = fcl.farm_crop_id
                JOIN Farms f ON f.farm_id = fc.farm_id
                SET fcl.farm_crop_id = %s, fcl.labour_id = %s, fcl.work_date = %s,
                    fcl.worker_count = %s, fcl.days_worked = %s, fcl.total_cost = %s
                WHERE fcl.labour_usage_id = %s AND f.farmer_id = %s
                """,
                (farm_crop_id, labour_id, work_date, worker_count, days_worked, total_cost, labour_usage_id, farmer_id),
            )
            connection.commit()
            return {"message": "Labour usage record updated successfully."}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()


def handle_edit_subsidy(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    farmer_subsidy_id = required_id(payload, "farmer_subsidy_id", "Subsidy Application")
    subsidy_id = required_id(payload, "subsidy_id", "Subsidy Scheme")
    application_date = (payload.get("application_date") or time.strftime("%Y-%m-%d")).strip()
    remarks = (payload.get("remarks") or "").strip()

    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            farmer_id = get_farmer_id(cursor, user["user_id"])
            cursor.execute(
                "SELECT farmer_subsidy_id, status FROM Farmer_Subsidies WHERE farmer_subsidy_id = %s AND farmer_id = %s",
                (farmer_subsidy_id, farmer_id),
            )
            row = cursor.fetchone()
            if not row:
                raise APIError(404, "Subsidy application not found or unauthorized.")
            if row["status"] != "PENDING":
                raise APIError(400, "Only PENDING subsidy applications can be edited.")

            cursor.execute(
                """
                UPDATE Farmer_Subsidies
                SET subsidy_id = %s, application_date = %s, remarks = %s
                WHERE farmer_subsidy_id = %s AND farmer_id = %s
                """,
                (subsidy_id, application_date, remarks, farmer_subsidy_id, farmer_id),
            )
            connection.commit()
            return {"message": "Subsidy application updated successfully."}
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()


def get_officer_stats(user: dict[str, Any]) -> dict[str, Any]:
    with database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT o.office_id, o.officer_id, o.panchayath_id, p.panchayath_name, ao.office_name, o.designation
                FROM Officers o
                JOIN Agriculture_Offices ao ON ao.office_id = o.office_id
                LEFT JOIN Panchayaths p ON p.panchayath_id = o.panchayath_id
                WHERE o.user_id = %s
                """,
                (user["user_id"],),
            )
            officer = cursor.fetchone()
            if not officer:
                raise APIError(403, "Complete your profile first.")

            office_id = officer["office_id"]
            panchayath_id = officer.get("panchayath_id")

            cursor.execute("SELECT COUNT(*) AS count FROM Panchayaths WHERE office_id = %s", (office_id,))
            panchayaths_count = cursor.fetchone()["count"]

            cursor.execute(
                """
                SELECT COUNT(DISTINCT f.farmer_id) AS farmers_count
                FROM Farmers f
                JOIN Panchayaths p ON p.panchayath_id = f.panchayath_id
                WHERE p.office_id = %s
                """,
                (office_id,),
            )
            farmers_count = cursor.fetchone()["farmers_count"]

            cursor.execute(
                """
                SELECT COUNT(DISTINCT farms.farm_id) AS farms_count
                FROM Farms farms
                JOIN Farmers f ON f.farmer_id = farms.farmer_id
                JOIN Panchayaths p ON p.panchayath_id = f.panchayath_id
                WHERE p.office_id = %s
                """,
                (office_id,),
            )
            farms_count = cursor.fetchone()["farms_count"]

            if panchayath_id:
                cursor.execute(
                    """
                    SELECT COUNT(DISTINCT fs.farmer_subsidy_id) AS pending_subsidies
                    FROM Farmer_Subsidies fs
                    JOIN Farmers f ON f.farmer_id = fs.farmer_id
                    WHERE f.panchayath_id = %s AND fs.status = 'PENDING'
                    """,
                    (panchayath_id,),
                )
            else:
                cursor.execute(
                    """
                    SELECT COUNT(DISTINCT fs.farmer_subsidy_id) AS pending_subsidies
                    FROM Farmer_Subsidies fs
                    JOIN Farmers f ON f.farmer_id = fs.farmer_id
                    JOIN Panchayaths p ON p.panchayath_id = f.panchayath_id
                    WHERE p.office_id = %s AND fs.status = 'PENDING'
                    """,
                    (office_id,),
                )
            pending_subsidies = cursor.fetchone()["pending_subsidies"]

            return {
                "office_id": office_id,
                "office_name": officer["office_name"],
                "panchayath_id": panchayath_id,
                "panchayath_name": officer.get("panchayath_name"),
                "designation": officer["designation"],
                "panchayaths_count": panchayaths_count,
                "farmers_count": farmers_count,
                "farms_count": farms_count,
                "pending_subsidies": pending_subsidies,
            }
        finally:
            cursor.close()


def json_response(
    start_response: Any,
    status: int,
    payload: dict[str, Any],
) -> list[bytes]:
    body = json.dumps(payload, default=str).encode("utf-8")
    start_response(
        f"{status} {HTTPStatus(status).phrase}",
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
            ("Access-Control-Allow-Origin", "*"),
            ("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type, Authorization, Accept"),
        ],
    )
    return [body]


def serve_frontend(path: str, start_response: Any) -> list[bytes]:
    relative_path = unquote(path).lstrip("/") or "index.html"
    target = (FRONTEND_DIR / relative_path).resolve()
    try:
        target.relative_to(FRONTEND_DIR.resolve())
    except ValueError:
        raise APIError(404, "Page not found.")
    if not target.is_file():
        raise APIError(404, "Page not found.")

    content = target.read_bytes()
    content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    if content_type.startswith("text/") or content_type in (
        "application/javascript",
        "application/json",
    ):
        content_type += "; charset=utf-8"
    start_response(
        "200 OK",
        [
            ("Content-Type", content_type),
            ("Content-Length", str(len(content))),
            ("X-Content-Type-Options", "nosniff"),
        ],
    )
    return [content]


def application(environ: dict[str, Any], start_response: Any) -> list[bytes]:
    path = urlsplit(environ.get("PATH_INFO", "/")).path
    method = environ.get("REQUEST_METHOD", "GET").upper()

    if method == "OPTIONS":
        start_response(
            "204 No Content",
            [
                ("Access-Control-Allow-Origin", "*"),
                ("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS"),
                ("Access-Control-Allow-Headers", "Content-Type, Authorization, Accept"),
            ],
        )
        return []

    try:
        if not path.startswith("/api/"):
            if method != "GET":
                raise APIError(405, "Method not allowed.")
            return serve_frontend(path, start_response)

        if path == "/api/health" and method == "GET":
            init_database_if_needed()
            with database_connection() as connection:
                connection.ping(reconnect=False, attempts=1, delay=0)
            return json_response(start_response, 200, {"status": "ok", "database": "connected"})

        if path == "/api/auth/register" and method == "POST":
            status, result = handle_register(parse_json_body(environ))
            return json_response(start_response, status, result)

        if path == "/api/auth/login" and method == "POST":
            return json_response(
                start_response, 200, handle_login(parse_json_body(environ))
            )

        if path == "/api/users/complete-profile" and method == "POST":
            user = authenticated_user(environ)
            result = handle_complete_profile(parse_json_body(environ), user)
            return json_response(start_response, 200, result)

        if path == "/api/users/profile" and method in ("PUT", "POST"):
            user = authenticated_user(environ)
            result = handle_update_profile(parse_json_body(environ), user)
            return json_response(start_response, 200, result)

        if path == "/api/seed" and method == "GET":
            with database_connection() as connection:
                seed_catalog_data(connection)
            return json_response(start_response, 200, {"status": "ok", "message": "Master catalog seeded successfully."})

        if path in ("/api/panchayaths", "/api/offices") and method == "GET":
            return json_response(start_response, 200, get_lookup_data(path))

        if path == "/api/reference-data" and method == "GET":
            authenticated_user(environ)
            init_database_if_needed()
            return json_response(start_response, 200, get_reference_data())

        # Farmer endpoints
        if path == "/api/farmer/overview" and method == "GET":
            user = authenticated_user(environ, "FARMER")
            return json_response(start_response, 200, get_farmer_overview(user))

        if path == "/api/farmer/farms" and method == "POST":
            user = authenticated_user(environ, "FARMER")
            result = handle_add_farm(parse_json_body(environ), user)
            return json_response(start_response, 201, result)

        if path in ("/api/farmer/farms", "/api/farmer/farms/edit") and (method == "PUT" or (method == "POST" and path.endswith("/edit"))):
            user = authenticated_user(environ, "FARMER")
            result = handle_edit_farm(parse_json_body(environ), user)
            return json_response(start_response, 200, result)

        if path == "/api/farmer/crops" and method == "POST":
            user = authenticated_user(environ, "FARMER")
            result = handle_plant_crop(parse_json_body(environ), user)
            return json_response(start_response, 201, result)

        if path in ("/api/farmer/crops", "/api/farmer/crops/edit") and (method == "PUT" or (method == "POST" and path.endswith("/edit"))):
            user = authenticated_user(environ, "FARMER")
            result = handle_edit_crop(parse_json_body(environ), user)
            return json_response(start_response, 200, result)

        if path == "/api/farmer/expenses" and method == "POST":
            user = authenticated_user(environ, "FARMER")
            result = handle_add_expense(parse_json_body(environ), user)
            return json_response(start_response, 201, result)

        if path in ("/api/farmer/expenses", "/api/farmer/expenses/edit") and (method == "PUT" or (method == "POST" and path.endswith("/edit"))):
            user = authenticated_user(environ, "FARMER")
            result = handle_edit_expense(parse_json_body(environ), user)
            return json_response(start_response, 200, result)

        if path == "/api/farmer/income" and method == "POST":
            user = authenticated_user(environ, "FARMER")
            result = handle_add_income(parse_json_body(environ), user)
            return json_response(start_response, 201, result)

        if path in ("/api/farmer/income", "/api/farmer/income/edit") and (method == "PUT" or (method == "POST" and path.endswith("/edit"))):
            user = authenticated_user(environ, "FARMER")
            result = handle_edit_income(parse_json_body(environ), user)
            return json_response(start_response, 200, result)

        if path == "/api/farmer/fertilizers" and method == "POST":
            user = authenticated_user(environ, "FARMER")
            result = handle_add_fertilizer(parse_json_body(environ), user)
            return json_response(start_response, 201, result)

        if path in ("/api/farmer/fertilizers", "/api/farmer/fertilizers/edit") and (method == "PUT" or (method == "POST" and path.endswith("/edit"))):
            user = authenticated_user(environ, "FARMER")
            result = handle_edit_fertilizer(parse_json_body(environ), user)
            return json_response(start_response, 200, result)

        if path == "/api/farmer/labour" and method == "POST":
            user = authenticated_user(environ, "FARMER")
            result = handle_add_labour(parse_json_body(environ), user)
            return json_response(start_response, 201, result)

        if path in ("/api/farmer/labour", "/api/farmer/labour/edit") and (method == "PUT" or (method == "POST" and path.endswith("/edit"))):
            user = authenticated_user(environ, "FARMER")
            result = handle_edit_labour(parse_json_body(environ), user)
            return json_response(start_response, 200, result)

        if path == "/api/farmer/subsidies" and method == "POST":
            user = authenticated_user(environ, "FARMER")
            result = handle_apply_subsidy(parse_json_body(environ), user)
            return json_response(start_response, 201, result)

        if path in ("/api/farmer/subsidies", "/api/farmer/subsidies/edit") and (method == "PUT" or (method == "POST" and path.endswith("/edit"))):
            user = authenticated_user(environ, "FARMER")
            result = handle_edit_subsidy(parse_json_body(environ), user)
            return json_response(start_response, 200, result)

        # Officer endpoints
        if path == "/api/officer/farmers" and method == "GET":
            user = authenticated_user(environ, "OFFICER")
            result = get_officer_farmers(user, environ.get("QUERY_STRING", ""))
            return json_response(start_response, 200, result)

        if path == "/api/officer/records" and method == "GET":
            user = authenticated_user(environ, "OFFICER")
            result = get_officer_records(user, environ.get("QUERY_STRING", ""))
            return json_response(start_response, 200, result)

        if path == "/api/officer/farmer-details" and method == "GET":
            user = authenticated_user(environ, "OFFICER")
            params = parse_qs(environ.get("QUERY_STRING", ""))
            farmer_id_val = params.get("farmer_id", [""])[0]
            if not farmer_id_val or not farmer_id_val.isdigit():
                raise APIError(400, "farmer_id query parameter is required.")
            result = get_officer_farmer_details(int(farmer_id_val))
            return json_response(start_response, 200, result)

        if path == "/api/officer/subsidies" and method == "GET":
            user = authenticated_user(environ, "OFFICER")
            result = get_officer_subsidies(user)
            return json_response(start_response, 200, result)

        if path == "/api/officer/subsidies/review" and method == "POST":
            user = authenticated_user(environ, "OFFICER")
            result = handle_review_subsidy(parse_json_body(environ), user)
            return json_response(start_response, 200, result)

        if path == "/api/officer/stats" and method == "GET":
            user = authenticated_user(environ, "OFFICER")
            result = get_officer_stats(user)
            return json_response(start_response, 200, result)

        if path.startswith("/api/"):
            raise APIError(404, "API endpoint not found.")
        raise APIError(405, "Method not allowed.")
    except APIError as error:
        return json_response(
            start_response, error.status, {"message": error.message}
        )
    except mysql.connector.Error as error:
        print(f"MySQL request failed: {error}", file=sys.stderr)
        return json_response(
            start_response,
            500,
            {"message": "A database operation failed. Check the backend log."},
        )
    except Exception as error:
        print(f"Unhandled request error: {error}", file=sys.stderr)
        return json_response(
            start_response, 500, {"message": "The server encountered an unexpected error."}
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Farm Portal running at http://127.0.0.1:{port}")
    print("Press Ctrl+C to stop.")
    with make_server("127.0.0.1", port, application) as server:
        server.serve_forever()
