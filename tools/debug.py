"""Quick device dump for debugging."""
import os
import sqlite3
import json

_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'db', 'configforge.db')

conn = sqlite3.connect(_DB)
rows = conn.execute('SELECT data FROM devices').fetchall()
for (data,) in rows:
    d = json.loads(data)
    print(d.get('IP'), '|', repr(d.get('Collector Region')), '|', d.get('Device'))
conn.close()
