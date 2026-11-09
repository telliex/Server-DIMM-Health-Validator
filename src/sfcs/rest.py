"""Example JSON REST contract. Adapt mappings for an authorized target service."""
import json
import os
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from . import SFCSError, RetryableError, ConflictError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class RestSFCSAdapter:
    def __init__(self, base_url, endpoints=None, token_env=None,
                 auth_header='Authorization', auth_scheme='Bearer', timeout=10):
        parsed = urlsplit(base_url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Invalid SFCS base URL')
        if parsed.scheme != 'https' and parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('HTTPS required except for loopback tests')
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 120:
            raise ValueError('timeout must be 0..120 seconds')
        if not auth_header or any(c in auth_header for c in '\r\n:') or any(c in auth_scheme for c in '\r\n'):
            raise ValueError('Invalid authentication configuration')
        self.base_url, self.timeout = base_url.rstrip('/'), timeout
        self.token_env, self.auth_header, self.auth_scheme = token_env, auth_header, auth_scheme
        self.endpoints = {'unit': '/units/{serial_number}', 'station': '/station-validation',
                          'result': '/results', 'history': '/units/{serial_number}/history'}
        self.endpoints.update(endpoints or {})
        for path in self.endpoints.values():
            if not isinstance(path, str) or not path.startswith('/') or path.startswith('//') or '?' in path or '#' in path or '\\' in path or '..' in path.split('/'):
                raise ValueError('Endpoints must be local absolute paths')
        self.opener = build_opener(NoRedirect())

    def _request(self, key, payload=None, serial_number=None, run_id=None):
        path = self.endpoints[key].format(serial_number=quote(serial_number or '', safe=''))
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
        if self.token_env:
            token = os.environ.get(self.token_env)
            if not token or '\r' in token or '\n' in token:
                raise SFCSError('SFCS authentication environment variable missing or invalid')
            headers[self.auth_header] = (self.auth_scheme + ' ' + token).strip()
        if run_id:
            headers['Idempotency-Key'] = run_id
        request = Request(self.base_url + path, headers=headers,
                          data=None if payload is None else json.dumps(payload, allow_nan=False).encode())
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise SFCSError('SFCS response too large')
            value = json.loads(raw)
        except HTTPError as exc:
            if exc.code in (408, 429) or 500 <= exc.code <= 599:
                raise RetryableError(f'SFCS temporary HTTP {exc.code}') from None
            if exc.code == 409:
                raise ConflictError('SFCS Run ID conflict') from None
            raise SFCSError(f'SFCS HTTP {exc.code}') from None
        except (URLError, TimeoutError, socket.timeout, ConnectionError):
            raise RetryableError('SFCS connection failure or timeout') from None
        except (ValueError, UnicodeError):
            raise SFCSError('Invalid SFCS JSON response') from None
        if not isinstance(value, list if key == 'history' else dict):
            raise SFCSError('Invalid SFCS response shape')
        return value

    def get_unit(self, serial_number):
        return self._request('unit', serial_number=serial_number)

    def validate_station(self, serial_number, station):
        return self._request('station', {'serial_number': serial_number, 'station': station})

    def upload_result(self, test_result):
        return self._request('result', test_result, run_id=test_result['run_id'])

    def get_test_history(self, serial_number):
        return self._request('history', serial_number=serial_number)
