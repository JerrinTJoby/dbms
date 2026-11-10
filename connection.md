# Application Connections

This document describes the connections present in the Farm Portal codebase:
how the browser reaches the application, how the application reaches MySQL,
how the database tables relate, and how the services are wired for local and
container-based hosting.

## Connection overview

```text
Browser pages (HTML, CSS, JavaScript)
        |
        | same-origin HTTP requests: /api/...
        v
Flask application / WSGI gateway (backend/app.py)
        |
        | MySQL Connector/Python, TCP (default port 3306)
        v
MySQL database: AgricultureDB
```

In the deployed/container setup, the browser connects to the web service's
public origin. The web service connects to MySQL over the Docker network. The
browser does not connect directly to MySQL.

## 1. Browser-to-backend connection

- The pages in `frontend/` load `styles.css` and `app.js` from the same
  application origin.
- `backend/app.py` serves those frontend files and handles API requests in
  the same process. Requests beginning with `/api/` are dispatched to API
  handlers; other `GET` requests serve frontend files.
- `frontend/app.js` uses `fetch()` through the shared `apiRequest()` helper.
  When served by the backend, API paths are relative (for example,
  `/api/auth/login`), so the page and API share an origin.
- If a page is opened directly using `file://`, the frontend helper points to
  `http://127.0.0.1:8000`, but the application instructs users to open the
  site through the backend instead.
- API responses include permissive CORS headers. Normal use is same-origin;
  no separate frontend web server or CORS setup is required.

### API connections

All endpoints below are handled by `backend/app.py`. Endpoints marked
**authenticated** expect the frontend to send the login token as a bearer
token in the `Authorization` header. Farmer and officer routes also enforce
the corresponding user role.

| Route | Methods | Purpose |
|---|---|---|
| `/api/health` | `GET` | Checks that the backend can connect to MySQL. |
| `/api/auth/register` | `POST` | Registers a farmer or officer account. |
| `/api/auth/login` | `POST` | Verifies credentials and returns a login token and user data. |
| `/api/users/complete-profile` | `POST` | **Authenticated.** Completes the user's role-specific profile. |
| `/api/users/profile` | `POST`, `PUT` | **Authenticated.** Updates the user's profile. |
| `/api/seed` | `GET` | Seeds master catalog data. |
| `/api/panchayaths` | `GET` | Returns Panchayath lookup data. |
| `/api/offices` | `GET` | Returns agriculture office lookup data. |
| `/api/reference-data` | `GET` | **Authenticated.** Returns reference/catalog data. |
| `/api/farmer/overview` | `GET` | **Farmer.** Returns the farmer's dashboard overview. |
| `/api/farmer/farms` | `POST`, `PUT` | **Farmer.** Creates or updates a farm. |
| `/api/farmer/farms/edit` | `POST` | **Farmer.** Alternate farm update route. |
| `/api/farmer/crops` | `POST`, `PUT` | **Farmer.** Creates or updates crop records. |
| `/api/farmer/crops/edit` | `POST` | **Farmer.** Alternate crop update route. |
| `/api/farmer/expenses` | `POST`, `PUT` | **Farmer.** Creates or updates expense records. |
| `/api/farmer/expenses/edit` | `POST` | **Farmer.** Alternate expense update route. |
| `/api/farmer/income` | `POST`, `PUT` | **Farmer.** Creates or updates income records. |
| `/api/farmer/income/edit` | `POST` | **Farmer.** Alternate income update route. |
| `/api/farmer/fertilizers` | `POST`, `PUT` | **Farmer.** Creates or updates fertilizer application records. |
| `/api/farmer/fertilizers/edit` | `POST` | **Farmer.** Alternate fertilizer update route. |
| `/api/farmer/labour` | `POST`, `PUT` | **Farmer.** Creates or updates labour records. |
| `/api/farmer/labour/edit` | `POST` | **Farmer.** Alternate labour update route. |
| `/api/farmer/subsidies` | `POST`, `PUT` | **Farmer.** Applies for or updates subsidy applications. |
| `/api/farmer/subsidies/edit` | `POST` | **Farmer.** Alternate subsidy update route. |
| `/api/officer/farmers` | `GET` | **Officer.** Lists farmers in the officer's jurisdiction. |
| `/api/officer/records` | `GET` | **Officer.** Reads jurisdiction records by requested type. |
| `/api/officer/farmer-details` | `GET` | **Officer.** Returns details for a requested farmer. |
| `/api/officer/subsidies` | `GET` | **Officer.** Lists subsidies for review. |
| `/api/officer/subsidies/review` | `POST` | **Officer.** Reviews a subsidy application. |
| `/api/officer/stats` | `GET` | **Officer.** Returns dashboard statistics. |

Unknown `/api/...` paths return an API not-found response. Query parameters
are used for filtering and selecting records, such as `farmer_id` on
`/api/officer/farmer-details`.

## 2. Browser session and authentication connection

- Successful login returns a signed token. The frontend stores it in browser
  `localStorage` as `authToken` and stores the user data as `user`.
- Authenticated API calls send that token as a bearer token. The backend
  verifies its signature and expiry before accessing protected endpoints.
- Tokens are configured to expire after 12 hours.
- Logging out or invalidating the local session removes both stored values.
- Registration passwords are stored as PBKDF2-HMAC-SHA256 hashes; the original
  password is not stored in the database.

## 3. Backend-to-MySQL connection

- The backend uses `mysql-connector-python` to connect to MySQL.
- Connection settings are read from the process environment. A
  `backend/.env` file is loaded when present. URL-style settings are checked in
  this order: `DATABASE_URL`, `MYSQL_URL`, then `MYSQL_PRIVATE_URL`.
- If no URL is set, the backend reads:

  | Setting | Alternate | Default |
  |---|---|---|
  | `DB_HOST` | `MYSQLHOST` | `127.0.0.1` |
  | `DB_PORT` | `MYSQLPORT` | `3306` |
  | `DB_NAME` | `MYSQLDATABASE` | `AgricultureDB` |
  | `DB_USER` | `MYSQLUSER` | empty (database access is unavailable until configured) |
  | `DB_PASSWORD` | `MYSQLPASSWORD` | application fallback value; configure a private value for deployment |

- The application creates a connection for database work and closes it when
  that operation finishes; it does not maintain a shared connection pool.
- Startup/health initialization checks for required tables and can initialize
  the schema or seed the master catalog when needed.
- `GET /api/health` reports a successful database connection as
  `{"status":"ok","database":"connected"}`. Database connection failures are
  logged by the backend and returned as an API error.
- SQL uses the `AgricultureDB` schema defined in `backend/schema.sql`.
  Initial catalog entries are supplied by `backend/seed_catalog.sql`.

## 4. Database table relationships

The foreign keys in `backend/schema.sql` connect the data as follows:

- `Users` has one role-specific profile in `Farmers` or `Officers`.
- `Agriculture_Offices` has many `Panchayaths`; officers are assigned to an
  office and may also be linked to a Panchayath. Farmers are linked to a
  Panchayath.
- `Farmers` own `Farms`. A farm has crop-season records in `Farm_Crops`, each
  linked to a catalog entry in `Crops`.
- Crop-season records can be linked to labour entries in
  `Farm_Crop_Labour`/`Labour_Types`, fertilizer applications in
  `Farm_Crop_Fertilizer`/`Fertilizers`, and sales in `Income`.
- `Expenses` link to a farm and can optionally reference a farm-crop record,
  rental type, or energy type. Rental and energy catalogs are
  `Rental_Types` and `Energy_Types`.
- `Farmers` apply for catalog entries in `Subsidies` through
  `Farmer_Subsidies`; an application can optionally record the reviewing
  `Officer`.
- The schema also defines the `Officer_Farmer_Directory` view for officer
  directory data.

## 5. Hosting and service connections

### Docker Compose

- `docker-compose.yml` defines a MySQL 8 service named `db` and an application
  service named `web`.
- The `web` service reaches MySQL at host `db` on port `3306`; Compose service
  discovery provides this hostname on the private Compose network.
- MySQL's port is published as `3306` for host access. The web app's port
  `8000` is published for browser access.
- The database uses the persistent `db_data` volume. The schema and catalog
  seed SQL files are mounted into MySQL's initialization directory.

### Application process

- `Dockerfile` installs the Python dependencies and runs the WSGI application
  with Gunicorn on `0.0.0.0:${PORT:-8000}`.
- `Procfile` also starts Gunicorn with `backend.app:application`, binding to
  the host-provided `PORT`.
- When run directly with `python backend/app.py`, the development server uses
  `PORT` (default `8000`) and listens on `127.0.0.1`.
- For deployments such as Railway, configure the database URL or MySQL
  environment variables and a private `APP_SECRET_KEY` in the hosting
  environment; do not rely on development credentials or fallback secrets.

## External service connections

No third-party API, email, payment, or cloud-storage client connections were
identified in the application code. The external runtime dependencies
documented here are the browser, the Flask/Gunicorn application, and MySQL.
