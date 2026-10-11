# Farm Portal backend

The browser UI and API are served from the same Python process, so the
frontend's relative `/api/...` requests reach this backend without a separate
web server or CORS configuration.

## 1. Prepare MySQL

Create a MySQL user and database, then run `schema.sql` once using MySQL
Workbench or the MySQL command-line client. The schema creates
`AgricultureDB` if it does not exist and does not drop an existing database.
Populate `Agriculture_Offices` and `Panchayaths` before creating profiles; the
profile form's dropdowns read from those tables.

## 2. Configure the backend

From the project folder, copy `backend/.env.example` to `backend/.env` and
replace the MySQL username/password:

```powershell
Copy-Item backend\.env.example backend\.env
```

Set `APP_SECRET_KEY` to a private random value of at least 32 characters; for
example, generate one with:

```powershell
& "C:\Program Files\Python314\python.exe" -c "import secrets; print(secrets.token_hex(32))"
```

Keep the generated value only in `backend/.env`. That file is ignored by Git.

Install the Python dependency:

```powershell
& "C:\Program Files\Python314\python.exe" -m pip install -r backend\requirements.txt
```

Start the web server:

```powershell
& "C:\Program Files\Python314\python.exe" backend\app.py
```

Open `http://127.0.0.1:8000`. Do not open the HTML files through `file://` or
another development server; they need to be served from this backend origin.
`GET /api/health` reports whether the backend can connect to MySQL.

## 3. How the connection works

1. The pages make same-origin `fetch()` requests from `frontend/app.js`.
2. `backend/app.py` routes `/api/...` requests to Python handlers and serves
   the HTML, CSS, JavaScript, and public images for other paths.
3. Each handler opens a MySQL connection using `DB_HOST`, `DB_PORT`, `DB_NAME`,
   `DB_USER`, and `DB_PASSWORD` from the process environment or `backend/.env`.
   Connections are closed after each operation; values in SQL statements use
   MySQL Connector/Python parameter placeholders.
4. Registration inserts `Users` with a PBKDF2-HMAC-SHA256 password hash.
   Login returns a signed, 12-hour bearer token and the user profile.
5. Profile completion inserts the role-specific `Farmers` or `Officers` row
   and completes the `Users` row in one database transaction.
6. Authenticated lookups populate the Panchayath and office dropdowns. The
   officer directory is limited to the officer's own office, and the farmer
   overview reads that farmer's farms and crop statuses.

## API routes used by the frontend

- `POST /api/auth/register` — `{ "email", "password", "role" }`
- `POST /api/auth/login` — `{ "email", "password" }`
- `POST /api/users/complete-profile` — authenticated, role-specific profile
- `GET /api/panchayaths` and `GET /api/offices` — authenticated lookups
- `GET /api/officer/farmers?panchayath_id=...` — officer's jurisdiction
- `GET /api/farmer/overview` — farmer's farms and crops
- `GET /api/health` — database connectivity check
