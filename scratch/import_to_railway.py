import os
import sys
import mysql.connector

# You can paste your Railway Public Connection details here:
# Found in Railway -> MySQL -> Connect -> Public Networking
RAILWAY_HOST = input("Enter Railway Host (e.g., viaduct.proxy.rlwy.net): ").strip()
RAILWAY_PORT = int(input("Enter Railway Port (e.g., 12345): ").strip())
RAILWAY_USER = input("Enter Railway User (usually root): ").strip() or "root"
RAILWAY_PASSWORD = input("Enter Railway Password: ").strip()
RAILWAY_DB = input("Enter Railway Database (usually railway): ").strip() or "railway"

print("\nConnecting to Railway MySQL...")
try:
    conn = mysql.connector.connect(
        host=RAILWAY_HOST,
        port=RAILWAY_PORT,
        user=RAILWAY_USER,
        password=RAILWAY_PASSWORD,
        database=RAILWAY_DB
    )
    cursor = conn.cursor()
    print("Connected successfully!")
except Exception as e:
    print(f"Connection failed: {e}")
    sys.exit(1)

def run_sql_file(filepath):
    print(f"\nImporting {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by semicolon to run each statement safely
    statements = [stmt.strip() for stmt in content.split(';') if stmt.strip()]
    for i, stmt in enumerate(statements, 1):
        if stmt.startswith('--'):
            # Filter pure comments
            lines = [l for l in stmt.splitlines() if not l.strip().startswith('--')]
            stmt = '\n'.join(lines).strip()
            if not stmt:
                continue
        try:
            cursor.execute(stmt)
        except Exception as e:
            print(f"Error on statement {i}: {e}")
    conn.commit()
    print(f"Finished importing {filepath}!")

run_sql_file("backend/schema.sql")
run_sql_file("backend/seed_catalog.sql")

print("\nAll tables and seed catalog data have been successfully created on Railway!")
conn.close()
