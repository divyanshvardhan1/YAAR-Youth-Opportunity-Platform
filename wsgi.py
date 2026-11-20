"""PythonAnywhere WSGI adapter for the Y.A.A.R. academic prototype.

This preserves the existing standard-library Python Handler (routes,
CSRF, sessions, database, and recommendation logic) without starting
an HTTP server. PythonAnywhere imports `application` from this module.
"""
import io
import os
from email.message import Message
from http import HTTPStatus

import app as project

# PythonAnywhere's public web app uses HTTPS; ensure cookies are secure.
project.COOKIE_SECURE = '; Secure'
project.init_db()


class RequestBridge(project.Handler):
    """Translate one WSGI request into the application's Handler interface."""
    def __init__(self, environ):
        self.environ = environ
        self.path = (environ.get('PATH_INFO') or '/') + (
            '?' + environ['QUERY_STRING'] if environ.get('QUERY_STRING') else ''
        )
        self.command = environ.get('REQUEST_METHOD', 'GET').upper()
        self.headers = Message()
        if environ.get('CONTENT_TYPE'):
            self.headers['Content-Type'] = environ['CONTENT_TYPE']
        if environ.get('CONTENT_LENGTH'):
            self.headers['Content-Length'] = environ['CONTENT_LENGTH']
        for key, val in environ.items():
            if key.startswith('HTTP_'):
                self.headers[key[5:].replace('_', '-')] = str(val)
        self.rfile = environ['wsgi.input']
        self.wfile = io.BytesIO()
        self.response_code = 200
        self.response_headers = []

    def send_response(self, code, message=None):
        self.response_code = int(code)
        self.response_headers = []

    def send_header(self, name, value):
        self.response_headers.append((name, str(value)))

    def end_headers(self):
        pass

    def send_error(self, code, message=None, explain=None):
        # Never expose application/server internals to public site visitors.
        data = f'{int(code)} - {HTTPStatus(int(code)).phrase}'.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def application(environ, start_response):
    request = RequestBridge(environ)
    try:
        if request.command == 'GET':
            request.do_GET()
        elif request.command == 'POST':
            request.do_POST()
        else:
            request.send_error(405)
        code = request.response_code
        reason = HTTPStatus(code).phrase
        start_response(f'{code} {reason}', request.response_headers)
        return [request.wfile.getvalue()]
    except Exception:
        # Let PythonAnywhere log the traceback; never show it to visitors.
        import traceback
        traceback.print_exc()
        body = b'Internal server error. Please contact the administrator.'
        start_response('500 Internal Server Error', [('Content-Type', 'text/plain; charset=utf-8'), ('Content-Length', str(len(body)))])
        return [body]
