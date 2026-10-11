import mysql.connector

conn = mysql.connector.connect(
    host='127.0.0.1',
    port=3306,
    user='root',
    password='Jerrin@!1530',
    database='AgricultureDB'
)
cur = conn.cursor()

# Get all base tables
cur.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
tables = [row[0] for row in cur.fetchall()]

print(f"Found {len(tables)} base tables in AgricultureDB:")
print(tables)

# Disable foreign key checks and truncate each table
cur.execute("SET FOREIGN_KEY_CHECKS = 0")
for table in tables:
    cur.execute(f"TRUNCATE TABLE `{table}`")
    print(f"Truncated `{table}`")
cur.execute("SET FOREIGN_KEY_CHECKS = 1")
conn.commit()

# Verify counts
print("\n--- Verification of row counts ---")
all_empty = True
for table in tables:
    cur.execute(f"SELECT COUNT(*) FROM `{table}`")
    count = cur.fetchone()[0]
    print(f"{table}: {count} rows")
    if count != 0:
        all_empty = False

if all_empty:
    print("\nSUCCESS: All tables have been completely cleared (0 rows).")
else:
    print("\nWARNING: Some tables still contain rows!")

conn.close()
