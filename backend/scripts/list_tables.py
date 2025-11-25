import sqlite3
import sys

db = 'backend/docfoundry.db'
if len(sys.argv) > 1:
    db = sys.argv[1]

conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
rows = cur.fetchall()
if not rows:
    print('No tables found or DB does not exist:', db)
else:
    for r in rows:
        print(r[0])
cur.close()
conn.close()
