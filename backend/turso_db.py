import requests as req
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime, timedelta

DB_URL = None
DB_TOKEN = None

class TursoRow(dict):
    def __getitem__(self, k):
        if isinstance(k, int):
            vals = list(super().values())
            return vals[k] if k < len(vals) else None
        return super().__getitem__(k)

    def __getattr__(self, k):
        if k in self:
            return self[k]
        raise AttributeError(k)

class TursoResult:
    def __init__(self, cols, rows, affected_row_count, last_insert_rowid):
        self._cols = [c['name'] for c in cols]
        self._rows = rows
        self._affected = affected_row_count
        self._last_rowid = last_insert_rowid
        self._index = 0

    @property
    def lastrowid(self):
        return self._last_rowid

    @property
    def rowcount(self):
        return len(self._rows)

    def fetchone(self):
        if self._rows:
            row = self._rows[0]
            return TursoRow(zip(self._cols, _convert_row(row)))
        return None

    def fetchall(self):
        return [TursoRow(zip(self._cols, _convert_row(r))) for r in self._rows]

    def __iter__(self):
        return self

    def __next__(self):
        if self._index < len(self._rows):
            row = self._rows[self._index]
            self._index += 1
            return TursoRow(zip(self._cols, _convert_row(row)))
        raise StopIteration

def _convert_row(row):
    result = []
    for cell in row:
        t = cell.get('type')
        v = cell.get('value')
        if t == 'integer':
            result.append(int(v) if v is not None else None)
        elif t == 'float':
            result.append(float(v) if v is not None else None)
        elif t == 'null':
            result.append(None)
        else:
            result.append(v)
    return result

_session = None

def _get_session():
    global _session
    if _session is None:
        _session = req.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504])
        _session.mount('https://', HTTPAdapter(max_retries=retries))
    return _session

class TursoDB:
    def __init__(self):
        self._baton = None

    def execute(self, sql, args=None):
        s = _get_session()
        url = DB_URL.replace('libsql://', 'https://')
        payload = {
            'requests': [
                {'type': 'execute', 'stmt': {'sql': sql, 'args': _convert_args(args)}}
            ]
        }
        if self._baton:
            payload['baton'] = self._baton

        r = s.post(f'{url}/v2/pipeline',
                    headers={'Authorization': f'Bearer {DB_TOKEN}', 'Content-Type': 'application/json'},
                    json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()

        if data.get('baton'):
            self._baton = data['baton']

        result = data['results'][0]
        if result['type'] == 'error':
            err = result.get('error', {}).get('message', 'Unknown error')
            raise Exception(f'Turso error: {err}')

        resp = result.get('response', {}).get('result', {})
        cols = resp.get('cols', [])
        rows = resp.get('rows', [])
        affected = resp.get('affected_row_count', 0)
        last_id = resp.get('last_insert_rowid')
        if last_id is not None:
            last_id = int(last_id)

        return TursoResult(cols, rows, affected, last_id)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

def _convert_args(args):
    if args is None:
        return []
    if isinstance(args, dict):
        return args
    result = []
    for a in args:
        if a is None:
            result.append({'type': 'null', 'value': None})
        elif isinstance(a, bool):
            result.append({'type': 'integer', 'value': '1' if a else '0'})
        elif isinstance(a, int):
            result.append({'type': 'integer', 'value': str(a)})
        elif isinstance(a, float):
            result.append({'type': 'float', 'value': str(a)})
        else:
            result.append({'type': 'text', 'value': str(a)})
    return result

def get_db():
    return TursoDB()

def init_db():
    sqls = [
        'CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE NOT NULL, phone TEXT DEFAULT \'\', password_hash TEXT NOT NULL, name TEXT DEFAULT \'\', avatar TEXT DEFAULT \'\', created_at TEXT DEFAULT (datetime(\'now\',\'localtime\')), updated_at TEXT DEFAULT (datetime(\'now\',\'localtime\')))',
        'CREATE TABLE IF NOT EXISTS auth_tokens (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, token TEXT UNIQUE NOT NULL, created_at TEXT DEFAULT (datetime(\'now\',\'localtime\')), expires_at TEXT, FOREIGN KEY (user_id) REFERENCES users(id))',
        'CREATE TABLE IF NOT EXISTS password_resets (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL, token TEXT UNIQUE NOT NULL, expires_at TEXT NOT NULL, used INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime(\'now\',\'localtime\')))',
        'CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT NOT NULL, description TEXT DEFAULT \'\', priority TEXT DEFAULT \'medium\', status TEXT DEFAULT \'pending\', due_date TEXT DEFAULT \'\', due_time TEXT DEFAULT \'\', category TEXT DEFAULT \'\', created_at TEXT DEFAULT (datetime(\'now\',\'localtime\')), updated_at TEXT DEFAULT (datetime(\'now\',\'localtime\')), FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE)',
        'CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT DEFAULT \'\', message TEXT NOT NULL, type TEXT DEFAULT \'info\', read INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime(\'now\',\'localtime\')), FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE)',
        'CREATE TABLE IF NOT EXISTS user_settings (user_id INTEGER PRIMARY KEY, theme TEXT DEFAULT \'light\', email_notifications INTEGER DEFAULT 1, push_notifications INTEGER DEFAULT 1, FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE)',
    ]
    db = get_db()
    for sql in sqls:
        db.execute(sql)
