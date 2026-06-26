
import sqlite3, json
conn = sqlite3.connect('snmp_yaml_generator.db')
rows = conn.execute('SELECT data FROM devices').fetchall()
for (data,) in rows:
    d = json.loads(data)
    print(d.get('IP'), '|', repr(d.get('Collector Region')), '|', d.get('Device'))
