import hashlib, secrets, os, re, smtplib, json
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, render_template

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)

app = Flask(__name__,
    template_folder=os.path.join(PROJECT, 'frontend'),
    static_folder=os.path.join(PROJECT, 'frontend', 'static'),
    static_url_path='/static')
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USER = os.environ.get('EMAIL_USER', '')
EMAIL_PASS = os.environ.get('EMAIL_PASS', '')
FROM_EMAIL = os.environ.get('FROM_EMAIL', 'noreply@taskmanager.com')
BASE_URL = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')

# ── Database ──
TURSO_DB_URL = os.environ.get('TURSO_DB_URL', '')
TURSO_DB_TOKEN = os.environ.get('TURSO_DB_TOKEN', '')

if TURSO_DB_URL and TURSO_DB_TOKEN:
    import turso_db
    turso_db.DB_URL = TURSO_DB_URL
    turso_db.DB_TOKEN = TURSO_DB_TOKEN
    get_db = turso_db.get_db
    init_db = turso_db.init_db
else:
    import sqlite3
    DB_DIR = os.path.join(PROJECT, 'database')
    DB = os.path.join(DB_DIR, 'tasks.db')
    os.makedirs(DB_DIR, exist_ok=True)

    def get_db():
        conn = sqlite3.connect(DB, timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_db():
        with get_db() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL, phone TEXT DEFAULT '',
                    password_hash TEXT NOT NULL, name TEXT DEFAULT '',
                    avatar TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    updated_at TEXT DEFAULT (datetime('now','localtime')));
                CREATE TABLE IF NOT EXISTS auth_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    expires_at TEXT, FOREIGN KEY (user_id) REFERENCES users(id));
                CREATE TABLE IF NOT EXISTS password_resets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL,
                    token TEXT UNIQUE NOT NULL, expires_at TEXT NOT NULL,
                    used INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now','localtime')));
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    title TEXT NOT NULL, description TEXT DEFAULT '',
                    priority TEXT DEFAULT 'medium', status TEXT DEFAULT 'pending',
                    due_date TEXT DEFAULT '', due_time TEXT DEFAULT '',
                    category TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    updated_at TEXT DEFAULT (datetime('now','localtime')),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                    title TEXT DEFAULT '', message TEXT NOT NULL,
                    type TEXT DEFAULT 'info', read INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY, theme TEXT DEFAULT 'light',
                    email_notifications INTEGER DEFAULT 1,
                    push_notifications INTEGER DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE);
            ''')
init_db()

# ── Helpers ──
def hash_password(password):
    salt = os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex()
    return f"{salt}${h}"

def verify_password(password, stored):
    salt, h = stored.split('$', 1)
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000).hex() == h

def gen_token():
    return secrets.token_hex(32)

def is_email(v):
    return bool(re.match(r'^[^@]+@[^@]+\.[^@]+$', v.strip()))

def send_email(to, subject, body):
    if not EMAIL_USER or not EMAIL_PASS:
        print(f"[EMAIL] To:{to} | {subject}")
        return True
    try:
        m = MIMEText(body, 'html')
        m['Subject'] = subject; m['From'] = FROM_EMAIL; m['To'] = to
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as s:
            s.starttls(); s.login(EMAIL_USER, EMAIL_PASS); s.send_message(m)
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}"); return False

def add_notification(user_id, title, message, type='info', conn=None):
    if conn:
        conn.execute('INSERT INTO notifications(user_id,title,message,type) VALUES(?,?,?,?)',
                     (user_id, title, message, type))
    else:
        with get_db() as c:
            c.execute('INSERT INTO notifications(user_id,title,message,type) VALUES(?,?,?,?)',
                      (user_id, title, message, type))

def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'No token'}), 401
        with get_db() as conn:
            r = conn.execute(
                'SELECT user_id FROM auth_tokens WHERE token=? AND (expires_at IS NULL OR expires_at>datetime("now","localtime"))',
                (token,)).fetchone()
        if not r:
            return jsonify({'error': 'Invalid token'}), 401
        return f(r['user_id'], *args, **kwargs)
    return wrapper

def row2dict(r):
    return dict(r) if r else None

# ── Auth ──
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dash():
    return render_template('dashboard.html')

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    d = request.get_json()
    email = (d.get('email') or '').strip().lower()
    phone = (d.get('phone') or '').strip()
    pwd = d.get('password', '')
    name = (d.get('name') or '').strip()
    if not email and not phone:
        return jsonify({'error': 'Email or phone required'}), 400
    if len(pwd) < 6:
        return jsonify({'error': 'Password min 6 characters'}), 400
    with get_db() as conn:
        if conn.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone():
            return jsonify({'error': 'Email already registered'}), 409
        pw_hash = hash_password(pwd)
        cur = conn.execute('INSERT INTO users(email,phone,password_hash,name) VALUES(?,?,?,?)',
                           (email, phone, pw_hash, name))
        uid = cur.lastrowid
        conn.execute('INSERT INTO user_settings(user_id) VALUES(?)', (uid,))
        token = gen_token()
        conn.execute('INSERT INTO auth_tokens(user_id,token) VALUES(?,?)', (uid, token))
        add_notification(uid, 'Welcome!', f'Welcome to task-manager, {name or email}!', 'success', conn)
        u = conn.execute('SELECT id,email,phone,name,created_at FROM users WHERE id=?', (uid,)).fetchone()
        return jsonify({'user': row2dict(u), 'token': token}), 201

@app.route('/api/auth/signin', methods=['POST'])
def signin():
    d = request.get_json()
    identifier = (d.get('identifier') or d.get('email') or '').strip().lower()
    pwd = d.get('password', '')
    if not identifier or not pwd:
        return jsonify({'error': 'Credentials required'}), 400
    with get_db() as conn:
        if is_email(identifier):
            u = conn.execute('SELECT * FROM users WHERE email=?', (identifier,)).fetchone()
        else:
            u = conn.execute('SELECT * FROM users WHERE phone=?', (identifier,)).fetchone()
        if not u or not verify_password(pwd, u['password_hash']):
            return jsonify({'error': 'Invalid credentials'}), 401
        token = gen_token()
        conn.execute('INSERT INTO auth_tokens(user_id,token) VALUES(?,?)', (u['id'], token))
        return jsonify({
            'user': {'id': u['id'], 'email': u['email'], 'phone': u['phone'], 'name': u['name'], 'created_at': u['created_at']},
            'token': token})

@app.route('/api/auth/forgot-password', methods=['POST'])
def forgot():
    d = request.get_json()
    email = (d.get('email') or '').strip().lower()
    if not email or not is_email(email):
        return jsonify({'error': 'Valid email required'}), 400
    with get_db() as conn:
        u = conn.execute('SELECT id,name FROM users WHERE email=?', (email,)).fetchone()
        if not u:
            return jsonify({'message': 'If email exists, a reset link was sent'})
        token = gen_token()
        expires = (datetime.now() + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
        conn.execute('INSERT INTO password_resets(email,token,expires_at) VALUES(?,?,?)', (email, token, expires))
        reset_url = f"{BASE_URL}/reset-password?token={token}"
        send_email(email, 'task-manager - Password Reset',
                   f'<h2>Reset Password</h2><p>Click: <a href="{reset_url}">{reset_url}</a></p><p>Valid 1 hour.</p>')
        return jsonify({'message': 'If email exists, a reset link was sent'})

@app.route('/api/auth/reset-password', methods=['POST'])
def reset():
    d = request.get_json()
    token = (d.get('token') or '').strip()
    pwd = d.get('password', '')
    if not token or len(pwd) < 6:
        return jsonify({'error': 'Invalid token or weak password'}), 400
    with get_db() as conn:
        r = conn.execute(
            'SELECT * FROM password_resets WHERE token=? AND used=0 AND expires_at>datetime("now","localtime")',
            (token,)).fetchone()
        if not r:
            return jsonify({'error': 'Invalid or expired token'}), 400
        conn.execute('UPDATE users SET password_hash=? WHERE email=?', (hash_password(pwd), r['email']))
        conn.execute('UPDATE password_resets SET used=1 WHERE id=?', (r['id'],))
        return jsonify({'message': 'Password reset successful'})

@app.route('/api/auth/me', methods=['GET'])
@require_auth
def get_me(uid):
    with get_db() as conn:
        u = conn.execute('SELECT id,email,phone,name,avatar,created_at FROM users WHERE id=?', (uid,)).fetchone()
        s = conn.execute('SELECT * FROM user_settings WHERE user_id=?', (uid,)).fetchone()
        return jsonify({'user': row2dict(u), 'settings': row2dict(s)})

@app.route('/api/auth/update-profile', methods=['PUT'])
@require_auth
def update_profile(uid):
    d = request.get_json()
    with get_db() as conn:
        conn.execute('UPDATE users SET name=?,phone=?,email=?,updated_at=datetime("now","localtime") WHERE id=?',
                     (d.get('name',''), d.get('phone',''), d.get('email',''), uid))
        conn.execute('UPDATE user_settings SET theme=?,email_notifications=?,push_notifications=? WHERE user_id=?',
                     (d.get('theme','light'), int(d.get('email_notifications',True)), int(d.get('push_notifications',True)), uid))
        u = conn.execute('SELECT id,email,phone,name,created_at FROM users WHERE id=?', (uid,)).fetchone()
        return jsonify({'user': row2dict(u)})

# ── Tasks ──
@app.route('/api/tasks', methods=['GET'])
@require_auth
def get_tasks(uid):
    sf = request.args.get('status','')
    pf = request.args.get('priority','')
    cf = request.args.get('category','')
    q = request.args.get('search','')
    df = request.args.get('date_from','')
    dt = request.args.get('date_to','')
    sql = 'SELECT * FROM tasks WHERE user_id=?'; p = [uid]
    if sf: sql += ' AND status=?'; p.append(sf)
    if pf: sql += ' AND priority=?'; p.append(pf)
    if cf: sql += ' AND category=?'; p.append(cf)
    if q: sql += ' AND (title LIKE ? OR description LIKE ?)'; p.extend([f'%{q}%', f'%{q}%'])
    if df: sql += ' AND due_date>=?'; p.append(df)
    if dt: sql += ' AND due_date<=?'; p.append(dt)
    sql += ' ORDER BY created_at DESC'
    with get_db() as conn:
        return jsonify([row2dict(r) for r in conn.execute(sql, p).fetchall()])

@app.route('/api/tasks', methods=['POST'])
@require_auth
def add_task(uid):
    d = request.get_json()
    title = (d.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'Title required'}), 400
    with get_db() as conn:
        cur = conn.execute(
            'INSERT INTO tasks(user_id,title,description,priority,due_date,due_time,category) VALUES(?,?,?,?,?,?,?)',
            (uid, title, d.get('description',''), d.get('priority','medium'),
             d.get('due_date',''), d.get('due_time',''), d.get('category','')))
        t = conn.execute('SELECT * FROM tasks WHERE id=?', (cur.lastrowid,)).fetchone()
        add_notification(uid, 'Task Created', f'Task "{title}" created', 'info', conn)
        return jsonify(row2dict(t)), 201

@app.route('/api/tasks/<int:tid>', methods=['PUT'])
@require_auth
def update_task(uid, tid):
    d = request.get_json()
    with get_db() as conn:
        t = conn.execute('SELECT * FROM tasks WHERE id=? AND user_id=?', (tid, uid)).fetchone()
        if not t:
            return jsonify({'error': 'Not found'}), 404
        conn.execute(
            'UPDATE tasks SET title=?,description=?,priority=?,status=?,due_date=?,due_time=?,category=?,updated_at=datetime("now","localtime") WHERE id=?',
            (d.get('title',t['title']), d.get('description',t['description']),
             d.get('priority',t['priority']), d.get('status',t['status']),
             d.get('due_date',t['due_date']), d.get('due_time',t['due_time']),
             d.get('category',t['category']), tid))
        return jsonify(row2dict(conn.execute('SELECT * FROM tasks WHERE id=?', (tid,)).fetchone()))

@app.route('/api/tasks/<int:tid>', methods=['DELETE'])
@require_auth
def delete_task(uid, tid):
    with get_db() as conn:
        if not conn.execute('SELECT id FROM tasks WHERE id=? AND user_id=?', (tid, uid)).fetchone():
            return jsonify({'error': 'Not found'}), 404
        conn.execute('DELETE FROM tasks WHERE id=?', (tid,))
        return jsonify({'message': 'Deleted'})

@app.route('/api/tasks/calendar', methods=['GET'])
@require_auth
def calendar_tasks(uid):
    m = request.args.get('month',''); y = request.args.get('year','')
    with get_db() as conn:
        sql = 'SELECT id,title,due_date,due_time,priority,status FROM tasks WHERE user_id=? AND due_date!=""'
        p = [uid]
        if m and y:
            sql += ' AND substr(due_date,6,2)=? AND substr(due_date,1,4)=?'
            p.extend([m.zfill(2), y])
        sql += ' ORDER BY due_date ASC'
        return jsonify([row2dict(r) for r in conn.execute(sql, p).fetchall()])

@app.route('/api/tasks/stats', methods=['GET'])
@require_auth
def task_stats(uid):
    with get_db() as conn:
        total = conn.execute('SELECT COUNT(*)c FROM tasks WHERE user_id=?', (uid,)).fetchone()['c']
        pending = conn.execute('SELECT COUNT(*)c FROM tasks WHERE user_id=? AND status="pending"', (uid,)).fetchone()['c']
        done = conn.execute('SELECT COUNT(*)c FROM tasks WHERE user_id=? AND status="completed"', (uid,)).fetchone()['c']
        overdue = conn.execute('SELECT COUNT(*)c FROM tasks WHERE user_id=? AND status="pending" AND due_date!="" AND due_date<date("now","localtime")', (uid,)).fetchone()['c']
        high = conn.execute('SELECT COUNT(*)c FROM tasks WHERE user_id=? AND priority="high" AND status="pending"', (uid,)).fetchone()['c']
        return jsonify({'total':total,'pending':pending,'completed':done,'overdue':overdue,'high_priority':high})

# ── Notifications ──
@app.route('/api/notifications', methods=['GET'])
@require_auth
def get_notifs(uid):
    with get_db() as conn:
        return jsonify([row2dict(r) for r in conn.execute(
            'SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 50', (uid,)).fetchall()])

@app.route('/api/notifications/<int:nid>/read', methods=['POST'])
@require_auth
def read_notif(uid, nid):
    with get_db() as conn:
        conn.execute('UPDATE notifications SET read=1 WHERE id=? AND user_id=?', (nid, uid))
        return jsonify({'message': 'OK'})

@app.route('/api/notifications/read-all', methods=['POST'])
@require_auth
def read_all(uid):
    with get_db() as conn:
        conn.execute('UPDATE notifications SET read=1 WHERE user_id=?', (uid,))
        return jsonify({'message': 'OK'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
