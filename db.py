"""RAAH local SQLite database (users, contacts, followed areas, reports, saved places, cache)."""
import sqlite3, time, json
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, un TEXT UNIQUE, salt TEXT, h TEXT, name TEXT, phone TEXT, area TEXT, city TEXT, state TEXT, emoji TEXT, joined TEXT);
CREATE TABLE IF NOT EXISTS contacts(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), name TEXT, rel TEXT, phone TEXT, status TEXT DEFAULT 'UNKNOWN', updated TEXT);
CREATE TABLE IF NOT EXISTS areas(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), name TEXT, admin TEXT, country TEXT, lat REAL, lon REAL, elev REAL, active INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), area TEXT, type TEXT, severity TEXT, text TEXT, created TEXT, status TEXT DEFAULT 'UNVERIFIED');
CREATE TABLE IF NOT EXISTS saved_places(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), name TEXT, kind TEXT, lat REAL, lon REAL);
CREATE TABLE IF NOT EXISTS checklist(user_id INTEGER, item INTEGER, PRIMARY KEY(user_id,item));
CREATE TABLE IF NOT EXISTS kv(user_id INTEGER, k TEXT, v TEXT, PRIMARY KEY(user_id,k));
CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, body TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS cities(name TEXT, state TEXT, lat REAL, lon REAL, elev REAL);
CREATE TABLE IF NOT EXISTS state_exposure(state TEXT PRIMARY KEY, flood REAL, cyclone REAL, landslide REAL, quake REAL, source TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, year INTEGER, name TEXT, type TEXT, states TEXT, impact TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS helplines(number TEXT PRIMARY KEY, label TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS plans(hazard TEXT, phase TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS calc_log(user_id INTEGER, area TEXT, date TEXT, hazard TEXT, score INTEGER, level TEXT, inputs TEXT, ts TEXT, PRIMARY KEY(user_id,area,date,hazard));
CREATE INDEX IF NOT EXISTS ix_contacts ON contacts(user_id); CREATE INDEX IF NOT EXISTS ix_areas ON areas(user_id);
"""


class DB:
    def __init__(s, path):
        s.c = sqlite3.connect(path, check_same_thread=False); s.c.row_factory = sqlite3.Row; s.c.executescript(SCHEMA); s.seed()

    def q(s, sql, a=()): return [dict(r) for r in s.c.execute(sql, a).fetchall()]
    def x(s, sql, a=()): cur = s.c.execute(sql, a); s.c.commit(); return cur.lastrowid
    def one(s, sql, a=()): r = s.q(sql, a); return r[0] if r else None

    # key-value (user_id 0 = app-wide, used for the logged-in session)
    def kget(s, uid, k, d=None): r = s.one('SELECT v FROM kv WHERE user_id=? AND k=?', (uid, k)); return json.loads(r['v']) if r else d
    def kset(s, uid, k, v): s.x('INSERT OR REPLACE INTO kv VALUES(?,?,?)', (uid, k, json.dumps(v)))

    # cache of API responses (lets the app show last saved data when offline)
    def cget(s, key): r = s.one('SELECT body,ts FROM cache WHERE key=?', (key,)); return (json.loads(r['body']), r['ts']) if r else None
    def cset(s, key, body): s.x('INSERT OR REPLACE INTO cache VALUES(?,?,?)', (key, json.dumps(body), time.time()))

    def areas(s, uid): return s.q('SELECT * FROM areas WHERE user_id=? ORDER BY id', (uid,))
    def add_area(s, uid, p):
        ex = s.one('SELECT id FROM areas WHERE user_id=? AND ABS(lat-?)<0.01 AND ABS(lon-?)<0.01', (uid, p['lat'], p['lon']))
        i = ex['id'] if ex else s.x('INSERT INTO areas(user_id,name,admin,country,lat,lon,elev) VALUES(?,?,?,?,?,?,?)', (uid, p['name'], p['admin'], p['country'], p['lat'], p['lon'], p.get('elev')))
        s.set_active(uid, i); return i
    def set_active(s, uid, i): s.x('UPDATE areas SET active=(id=?) WHERE user_id=?', (i, uid))
    def del_area(s, uid, i): s.x('DELETE FROM areas WHERE id=? AND user_id=?', (i, uid))
    def toggle_check(s, uid, i):
        if s.one('SELECT 1 FROM checklist WHERE user_id=? AND item=?', (uid, i)): s.x('DELETE FROM checklist WHERE user_id=? AND item=?', (uid, i))
        else: s.x('INSERT INTO checklist VALUES(?,?)', (uid, i))
    def checks(s, uid): return [r['item'] for r in s.q('SELECT item FROM checklist WHERE user_id=?', (uid,))]

    def seed(s):  # reference data (see seed_data.py) is loaded once
        import seed_data as d
        if s.one('SELECT 1 FROM cities'): return
        s.c.executemany('INSERT INTO cities VALUES(?,?,?,?,?)', d.CITIES)
        s.c.executemany('INSERT INTO state_exposure VALUES(?,?,?,?,?,?)', [(k, *v, 'Approx. from NDMA/GSI/BIS hazard atlases') for k, v in d.EXPOSURE.items()])
        s.c.executemany('INSERT INTO events(year,name,type,states,impact,source) VALUES(?,?,?,?,?,?)', [(*e, 'NDMA / media reports (approximate)') for e in d.EVENTS])
        s.c.executemany('INSERT INTO helplines VALUES(?,?,?)', d.HELPLINES)
        s.c.executemany('INSERT INTO plans VALUES(?,?,?)', [(h, ph, t) for h, v in d.PLANS.items() for ph, t in zip(('Before', 'During', 'After'), v)]); s.c.commit()

    def exposure(s, state):
        r = s.one('SELECT * FROM state_exposure WHERE lower(state)=lower(?)', (state or '',)); return dict(flood=r['flood'], storm=r['cyclone'], landslide=r['landslide'], quake=r['quake']) if r else None
    def events_count(s, state, typ): return s.one('SELECT COUNT(*) n FROM events WHERE type=? AND states LIKE ?', (typ, f'%{state}%'))['n']
    def helplines(s): return [(r['number'], r['label']) for r in s.q('SELECT * FROM helplines')]
    def plans(s):
        out = {}
        for r in s.q('SELECT * FROM plans'): out.setdefault(r['hazard'], []).append(f"{r['phase']}: {r['text']}")
        return {k: '\n'.join(v) for k, v in out.items()}
    def log_calc(s, uid, area, date, hz, score, level, inputs):
        s.x('INSERT OR REPLACE INTO calc_log VALUES(?,?,?,?,?,?,?,?)', (uid, area, date, hz, score, level, json.dumps(inputs), time.strftime('%Y-%m-%d %H:%M')))
