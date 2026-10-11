import mysql.connector

conn = mysql.connector.connect(
    host='127.0.0.1',
    port=3306,
    user='root',
    password='Jerrin@!1530',
    database='AgricultureDB'
)
cur = conn.cursor()

catalogs = [
    'agriculture_offices',
    'panchayaths',
    'crops',
    'fertilizers',
    'labour_types',
    'rental_types',
    'energy_types',
    'subsidies'
]

sql_lines = [
    '-- Master Catalog Seed Data',
    'USE AgricultureDB;',
    'SET FOREIGN_KEY_CHECKS = 0;'
]

for cat in catalogs:
    cur.execute(f'SELECT * FROM `{cat}`')
    rows = cur.fetchall()
    col_names = [d[0] for d in cur.description]
    cols_str = ', '.join([f'`{c}`' for c in col_names])
    sql_lines.append(f'\n-- {cat}')
    sql_lines.append(f'DELETE FROM `{cat}`;')
    for r in rows:
        val_strs = []
        for v in r:
            if v is None:
                val_strs.append('NULL')
            elif isinstance(v, (int, float)):
                val_strs.append(str(v))
            else:
                s = str(v).replace("'", "''")
                val_strs.append(f"'{s}'")
        values_joined = ', '.join(val_strs)
        sql_lines.append(f'INSERT INTO `{cat}` ({cols_str}) VALUES ({values_joined});')

sql_lines.append('\nSET FOREIGN_KEY_CHECKS = 1;')

with open('backend/seed_catalog.sql', 'w', encoding='utf-8') as f:
    f.write('\n'.join(sql_lines) + '\n')

print('Catalog seed script successfully written to backend/seed_catalog.sql')
conn.close()
