import sys, os, json, traceback
from io import BytesIO
from urllib.parse import urlencode

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
os.environ.setdefault('LAMBDA_TASK_ROOT', '1')

from app import app as flask_app

def handler(event, context):
    try:
        method = event.get('httpMethod', 'GET')
        path = event.get('path', '/')
        path = path.replace('/.netlify/functions/api', '/api')
        if not path.startswith('/api'):
            path = '/api' + path

        headers = {k.lower(): v for k, v in (event.get('headers') or {}).items()}
        qs = urlencode(event.get('queryStringParameters') or {})
        body = event.get('body') or ''
        if event.get('isBase64Encoded'):
            import base64
            body = base64.b64decode(body).decode('utf-8')

        environ = {
            'REQUEST_METHOD': method,
            'PATH_INFO': path,
            'QUERY_STRING': qs,
            'SERVER_NAME': 'netlify',
            'SERVER_PORT': '443',
            'SERVER_PROTOCOL': 'HTTP/1.1',
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'https',
            'wsgi.input': BytesIO(body.encode('utf-8')),
            'wsgi.errors': BytesIO(),
            'wsgi.multithread': False,
            'wsgi.multiprocess': False,
            'wsgi.run_once': True,
            'CONTENT_TYPE': headers.get('content-type', ''),
            'CONTENT_LENGTH': headers.get('content-length', str(len(body))),
            'HTTP_ACCEPT': headers.get('accept', ''),
        }
        for k, v in headers.items():
            key = k.upper().replace('-', '_')
            if key not in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
                environ[f'HTTP_{key}'] = v

        status_info = [200]
        resp_hdrs = [{}]

        def start_response(status, headers, exc_info=None):
            status_info[0] = int(status.split(' ')[0])
            resp_hdrs[0] = {k: v for k, v in headers}

        body_iter = flask_app.wsgi_app(environ, start_response)
        resp_body = b''.join(body_iter).decode('utf-8')

        return {'statusCode': status_info[0], 'headers': resp_hdrs[0], 'body': resp_body}
    except Exception as e:
        return {'statusCode': 500, 'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': str(e), 'traceback': traceback.format_exc()})}
