import psycopg2
import os

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/docfoundry')

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
rows = cur.fetchall()
if not rows:
    print('No tables found in public schema')
else:
    for r in rows:
        print(r[0])
cur.close()
conn.close()
