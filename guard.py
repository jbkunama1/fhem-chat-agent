import json, secrets, sqlite3, time

READS = {'fhem_get', 'fhem_get_readings', 'fhem_list_attrs', 'fhem_list_devices', 'fhem_device_search', 'fhem_reading_history'}

def readonly(name):
    return name in READS

class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS chats (owner TEXT PRIMARY KEY, messages TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS actions (id TEXT PRIMARY KEY, owner TEXT, payload TEXT, expires REAL, state TEXT)')
        self.db.execute("UPDATE actions SET state='cancelled' WHERE state='pending'")
        for owner, raw in self.db.execute('SELECT owner,messages FROM chats').fetchall():
            messages = json.loads(raw)
            resolved = {m.get('tool_call_id') for m in messages if m.get('role') == 'tool'}
            missing = [c['id'] for m in messages for c in m.get('tool_calls', []) if c['id'] not in resolved]
            for ident in missing:
                messages.append({'role':'tool','tool_call_id':ident,'content':json.dumps({'status':'interrupted','note':'Neustart: Ausgang unklar oder offene Freigabe storniert. Nicht automatisch wiederholen.'})})
            if missing:
                self.db.execute('UPDATE chats SET messages=? WHERE owner=?', (json.dumps(messages), owner))
        self.db.commit()

    def load(self, owner):
        row = self.db.execute('SELECT messages FROM chats WHERE owner=?', (owner,)).fetchone()
        return json.loads(row[0]) if row else []

    def save(self, owner, messages):
        self.db.execute('INSERT OR REPLACE INTO chats VALUES (?,?)', (owner, json.dumps(messages)))
        self.db.commit()

    def pending(self, owner):
        row = self.db.execute("SELECT id,payload,expires FROM actions WHERE owner=? AND state='pending' ORDER BY rowid DESC LIMIT 1", (owner,)).fetchone()
        return dict(id=row[0], action=json.loads(row[1]), expires=row[2]) if row else None

    def propose(self, owner, payload, ttl):
        ident = secrets.token_hex(16)
        self.db.execute('INSERT INTO actions VALUES (?,?,?,?,?)', (ident, owner, json.dumps(payload, sort_keys=True), time.time()+ttl, 'pending'))
        self.db.commit()
        return self.pending(owner)

    def claim(self, owner, ident, approve):
        with self.db:
            row = self.db.execute("SELECT payload,expires FROM actions WHERE id=? AND owner=? AND state='pending'", (ident, owner)).fetchone()
            if not row:
                raise ValueError('Freigabe fehlt, gehört einem anderen Benutzer oder wurde bereits verwendet.')
            state = 'expired' if row[1] < time.time() else ('consumed' if approve else 'rejected')
            cur = self.db.execute("UPDATE actions SET state=? WHERE id=? AND owner=? AND state='pending'", (state, ident, owner))
            if cur.rowcount != 1:
                raise ValueError('Freigabe bereits verwendet.')
        return json.loads(row[0]), state
