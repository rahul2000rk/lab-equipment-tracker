import os, sys, csv, io, time, sqlite3, secrets, threading, webbrowser, datetime as dt
from functools import wraps
from flask import Flask, g, request, jsonify, session, send_file, Response
from werkzeug.security import generate_password_hash, check_password_hash
from openpyxl import load_workbook

B = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get('DATA_DIR', B); os.makedirs(DATA, exist_ok=True)
DB, XL, PORT = os.path.join(DATA, 'lab.db'), os.path.join(B, 'data', 'equipment.xlsx'), int(os.environ.get('PORT', 8765))
CLOUD = bool(os.environ.get('PORT'))
app = Flask(__name__)
kf = os.path.join(DATA, 'secret.key')
if not os.environ.get('SECRET_KEY') and not os.path.exists(kf): open(kf, 'w').write(secrets.token_hex(32))
app.secret_key = os.environ.get('SECRET_KEY') or open(kf).read()
app.config.update(SESSION_COOKIE_SECURE=CLOUD, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
FAILS = {}
F = ['tag', 'name', 'category', 'make', 'model', 'serial', 'rng', 'location', 'cond', 'remarks', 'cal_last', 'cal_due', 'agency']
SCHEMA = """PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE COLLATE NOCASE, name TEXT, emp_id TEXT, role TEXT, pw TEXT, must_change INT DEFAULT 1, active INT DEFAULT 1);
CREATE TABLE IF NOT EXISTS equipment(id INTEGER PRIMARY KEY, tag TEXT UNIQUE COLLATE NOCASE, name TEXT, category TEXT, make TEXT, model TEXT, serial TEXT, rng TEXT, location TEXT, cond TEXT, remarks TEXT, cal_last TEXT, cal_due TEXT, agency TEXT, holder_id INT REFERENCES users(id), since TEXT);
CREATE TABLE IF NOT EXISTS log(id INTEGER PRIMARY KEY, ts TEXT, actor TEXT, action TEXT, tag TEXT, name TEXT, target TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v INT);
INSERT OR IGNORE INTO meta VALUES('ver',1);"""

def clean(v):
    s = str(v).strip() if v is not None else ''
    return '' if s.lower() in ('nil', 'n/a', 'none') else s
def dd(v):
    if isinstance(v, (int, float)): return (dt.date(1899, 12, 30) + dt.timedelta(days=int(v))).isoformat()
    return v.date().isoformat() if hasattr(v, 'date') else ''
def cat(n):
    n = n.lower()
    for k, c in (('multimeter', 'Multimeter'), ('oscilloscope', 'Oscilloscope'), ('power supply', 'Power Supply'), ('powersupply', 'Power Supply'),
                 ('solder', 'Soldering & Rework'), ('rework', 'Soldering & Rework'), ('hot air', 'Soldering & Rework'), ('glue', 'Soldering & Rework'),
                 ('generator', 'Signal Generator'), ('probe', 'Probes'), ('calibrator', 'Measurement'), ('meter', 'Measurement'),
                 ('tachometer', 'Measurement'), ('analyzer', 'Measurement')):
        if k in n: return c
    return 'Tools & Accessories'

def seed(c):
    wb = load_workbook(XL, data_only=True)
    cal = {str(r[2]).strip(): r for r in wb['Calibrated Equipment List'].iter_rows(min_row=2, values_only=True) if r[2]}
    oth = {(str(r[0]).strip().lower(), str(r[2]).strip()): r for r in wb['Other Equipments & Accessories'].iter_rows(min_row=2, values_only=True) if r[0]}
    ins = 'INSERT OR IGNORE INTO equipment(tag,name,category,make,model,serial,rng,location,cond,remarks,cal_last,cal_due,agency) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)'
    for r in wb['Equipment Details'].iter_rows(min_row=2, values_only=True):
        if not r[1]: continue
        sl, name, eid, make, model, ser, rng, loc = r[:8]
        name = str(name).strip(); tag = clean(eid) or f'LAB-{int(sl):03d}'
        o = oth.get((name.lower(), str(ser).strip())); k = cal.get(clean(eid))
        c.execute(ins, (tag, name, cat(name), clean(make), clean(model), clean(ser), clean(rng), clean(loc) or 'EDS Lab',
                        ('Need to Repair' if o and 'repair' in str(o[6]).lower() else str(o[4]).strip()) if o else 'Good', clean(o[6]) if o else '',
                        dd(k[7]) if k else '', dd(k[8]) if k else '', clean(k[9]) if k else ''))
    for r in wb['Keys & Other Details'].iter_rows(min_row=2, values_only=True):
        if not r[1]: continue
        kid = clean(r[2]); tag = f'KEY-{kid}' if kid else f'KEY-{int(r[0]):02d}'
        note = '; '.join(x for x in (('Handed over to ' + clean(r[4])) if clean(r[4]) else '', clean(r[5])) if x)
        c.execute(ins, (tag, str(r[1]).strip(), 'Keys', '', '', kid, '', clean(r[3]), 'Good', note, '', '', ''))

def init():
    c = sqlite3.connect(DB); c.executescript(SCHEMA)
    if not c.execute('SELECT 1 FROM users').fetchone():
        c.execute("INSERT INTO users(username,name,emp_id,role,pw,must_change) VALUES('admin','Lab Admin','','admin',?,1)", (generate_password_hash(os.environ.get('ADMIN_PASSWORD', 'admin123')),))
        seed(c)
    c.commit(); c.close()

def db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB, timeout=10); g.db.row_factory = sqlite3.Row
    return g.db
@app.teardown_appcontext
def _close(_):
    c = g.pop('db', None)
    if c: c.close()
def rows(sql, a=()): return [dict(r) for r in db().execute(sql, a).fetchall()]
def one(sql, a=()):
    r = db().execute(sql, a).fetchone(); return dict(r) if r else None
def now(): return dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def commit(action=None, eq=None, target='', note=''):
    c = db()
    if action:
        c.execute('INSERT INTO log(ts,actor,action,tag,name,target,note) VALUES(?,?,?,?,?,?,?)',
                  (now(), g.u['name'], action, eq['tag'] if eq else '', eq['name'] if eq else '', target, note))
    c.execute("UPDATE meta SET v=v+1 WHERE k='ver'"); c.commit()

def auth(admin=False):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            u = one('SELECT * FROM users WHERE id=? AND active=1', (session.get('uid', 0),))
            if not u: return jsonify(error='Not signed in'), 401
            u['admin'] = u['role'] == 'admin' and session.get('portal') == 'admin'
            if admin and not u['admin']: return jsonify(error='Admin only'), 403
            g.u = u; return f(*a, **k)
        return w
    return deco
def prof(u): return {k: u[k] for k in ('id', 'name', 'username', 'emp_id', 'role', 'admin', 'must_change')}

@app.get('/')
def index(): return send_file(os.path.join(B, 'index.html'))

@app.post('/api/login')
def login():
    j = request.get_json(force=True)
    key = str(j.get('username', '')).strip().lower(); n, t0 = FAILS.get(key, (0, 0))
    if time.time() - t0 > 300: n = 0
    if n >= 5: return jsonify(error='Too many failed attempts. Try again in 5 minutes'), 429
    u = one('SELECT * FROM users WHERE username=? AND active=1', (key,))
    if not u or not check_password_hash(u['pw'], j.get('password', '')):
        FAILS[key] = (n + 1, time.time()); return jsonify(error='Invalid username or password'), 401
    FAILS.pop(key, None)
    if j.get('portal') == 'admin' and u['role'] != 'admin': return jsonify(error='This account has no admin access'), 403
    session['uid'], session['portal'] = u['id'], ('admin' if j.get('portal') == 'admin' else 'user')
    u['admin'] = session['portal'] == 'admin'; return jsonify(prof(u))
@app.post('/api/logout')
def logout(): session.clear(); return jsonify(ok=1)
@app.get('/api/me')
@auth()
def me(): return jsonify(prof(g.u))
@app.get('/api/version')
@auth()
def ver(): return jsonify(v=one("SELECT v FROM meta WHERE k='ver'")['v'])

@app.post('/api/password')
@auth()
def pw():
    j = request.get_json(force=True)
    if not check_password_hash(g.u['pw'], j.get('old', '')): return jsonify(error='Current password is wrong'), 400
    if len(j.get('new', '')) < 6: return jsonify(error='New password needs at least 6 characters'), 400
    db().execute('UPDATE users SET pw=?, must_change=0 WHERE id=?', (generate_password_hash(j['new']), g.u['id'])); commit(); return jsonify(ok=1)

def eq_list(admin, uid):
    out = rows('SELECT e.*, u.name holder, u.emp_id holder_emp FROM equipment e LEFT JOIN users u ON u.id=e.holder_id ORDER BY e.category, e.tag')
    for e in out:
        e['status'] = 'Checked out' if e['holder_id'] else 'Available'; e['mine'] = e['holder_id'] == uid
        if not admin:
            for k in ('holder', 'holder_emp', 'holder_id', 'since'): e.pop(k)
    return out
@app.get('/api/equipment')
@auth()
def eq_get(): return jsonify(eq_list(g.u['admin'], g.u['id']))
def fields():
    j = request.get_json(force=True); return {k: str(j.get(k) or '').strip() for k in F}
@app.post('/api/equipment')
@auth(1)
def eq_add():
    d = fields()
    if not d['tag'] or not d['name']: return jsonify(error='ID and name are required'), 400
    try: db().execute('INSERT INTO equipment(%s) VALUES(%s)' % (','.join(F), ','.join('?' * len(F))), [d[k] for k in F])
    except sqlite3.IntegrityError: return jsonify(error='Equipment ID already exists'), 409
    commit('ADD', d); return jsonify(ok=1)
@app.put('/api/equipment/<int:i>')
@auth(1)
def eq_put(i):
    d = fields()
    if not one('SELECT 1 FROM equipment WHERE id=?', (i,)): return jsonify(error='Not found'), 404
    try: db().execute('UPDATE equipment SET ' + ','.join(k + '=?' for k in F) + ' WHERE id=?', [d[k] for k in F] + [i])
    except sqlite3.IntegrityError: return jsonify(error='Equipment ID already exists'), 409
    commit('EDIT', d); return jsonify(ok=1)
@app.delete('/api/equipment/<int:i>')
@auth(1)
def eq_del(i):
    e = one('SELECT * FROM equipment WHERE id=?', (i,))
    if not e: return jsonify(error='Not found'), 404
    db().execute('DELETE FROM equipment WHERE id=?', (i,)); commit('REMOVE', e); return jsonify(ok=1)
@app.post('/api/equipment/<int:i>/take')
@auth()
def take(i):
    e = one('SELECT * FROM equipment WHERE id=?', (i,))
    if not e: return jsonify(error='Not found'), 404
    if e['holder_id']: return jsonify(error='Already checked out by someone else'), 409
    if e['cond'] == 'Need to Repair': return jsonify(error='Item is flagged for repair'), 409
    db().execute('UPDATE equipment SET holder_id=?, since=? WHERE id=?', (g.u['id'], now(), i)); commit('CHECK-OUT', e, g.u['name']); return jsonify(ok=1)
@app.post('/api/equipment/<int:i>/return')
@auth()
def ret(i):
    e = one('SELECT * FROM equipment WHERE id=?', (i,))
    if not e: return jsonify(error='Not found'), 404
    if e['holder_id'] != g.u['id'] and not g.u['admin']: return jsonify(error='Not in your list'), 403
    h = one('SELECT name FROM users WHERE id=?', (e['holder_id'],)) if e['holder_id'] else None
    db().execute('UPDATE equipment SET holder_id=NULL, since=NULL WHERE id=?', (i,)); commit('RETURN', e, h['name'] if h else ''); return jsonify(ok=1)
@app.post('/api/equipment/<int:i>/assign')
@auth(1)
def assign(i):
    e = one('SELECT * FROM equipment WHERE id=?', (i,)); uid = (request.get_json(force=True) or {}).get('user_id')
    u = one('SELECT * FROM users WHERE id=? AND active=1', (uid,)) if uid else None
    if not e: return jsonify(error='Not found'), 404
    if uid and not u: return jsonify(error='User not found'), 404
    db().execute('UPDATE equipment SET holder_id=?, since=? WHERE id=?', (u['id'] if u else None, now() if u else None, i))
    commit('ASSIGN' if u else 'RETURN', e, u['name'] if u else ''); return jsonify(ok=1)

@app.get('/api/users')
@auth(1)
def users():
    return jsonify(rows('SELECT id,username,name,emp_id,role,active,(SELECT COUNT(*) FROM equipment WHERE holder_id=users.id) held FROM users ORDER BY name'))
@app.post('/api/users')
@auth(1)
def user_add():
    j = request.get_json(force=True); un, nm, p = (str(j.get(k, '')).strip() for k in ('username', 'name', 'password'))
    if not un or not nm or len(p) < 6: return jsonify(error='Username, name and a password (6+ chars) are required'), 400
    try: db().execute('INSERT INTO users(username,name,emp_id,role,pw) VALUES(?,?,?,?,?)',
                      (un, nm, str(j.get('emp_id', '')).strip(), 'admin' if j.get('role') == 'admin' else 'user', generate_password_hash(p)))
    except sqlite3.IntegrityError: return jsonify(error='Username already exists'), 409
    commit('USER-ADD', None, nm); return jsonify(ok=1)
@app.put('/api/users/<int:i>')
@auth(1)
def user_put(i):
    j = request.get_json(force=True); u = one('SELECT * FROM users WHERE id=?', (i,))
    if not u: return jsonify(error='Not found'), 404
    if 'active' in j:
        if i == g.u['id']: return jsonify(error="You can't deactivate yourself"), 400
        if not j['active'] and one('SELECT 1 FROM equipment WHERE holder_id=?', (i,)): return jsonify(error='User still holds equipment. Return or reassign it first'), 409
        db().execute('UPDATE users SET active=? WHERE id=?', (1 if j['active'] else 0, i))
    if j.get('password'):
        if len(j['password']) < 6: return jsonify(error='Password needs at least 6 characters'), 400
        db().execute('UPDATE users SET pw=?, must_change=1 WHERE id=?', (generate_password_hash(j['password']), i))
    commit('USER-EDIT', None, u['name']); return jsonify(ok=1)
@app.get('/api/log')
@auth(1)
def logs(): return jsonify(rows('SELECT * FROM log ORDER BY id DESC LIMIT 500'))
@app.get('/api/export.csv')
@auth(1)
def export():
    s = io.StringIO(); w = csv.writer(s); cols = F + ['status', 'holder', 'holder_emp', 'since']; w.writerow(cols)
    for e in eq_list(True, 0): w.writerow([e.get(k) or '' for k in cols])
    return Response(s.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=equipment_%s.csv' % dt.date.today()})

init()
if __name__ == '__main__':
    host = '0.0.0.0' if '--lan' in sys.argv else '127.0.0.1'; url = f'http://127.0.0.1:{PORT}'
    t = threading.Thread(target=lambda: app.run(host=host, port=PORT, threaded=True), daemon=True); t.start(); time.sleep(1)
    try:
        import webview; webview.create_window('Lab Equipment Tracker', url, width=1280, height=820); webview.start()
    except ImportError:
        print('Running at', url, '(Ctrl+C to stop)'); webbrowser.open(url)
        try: t.join()
        except KeyboardInterrupt: pass
