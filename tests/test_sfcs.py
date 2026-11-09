import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
import yaml
from src.config_loader import load_config
from src.connection import MockConnection
from src.sfcs import SFCSError, RetryableError, ConflictError
from src.sfcs.mock import MockSFCSAdapter
from src.sfcs.store import ResultStore
from src.sfcs.workflow import execute
from src.sfcs.delivery import Delivery
from src.sfcs.rest import RestSFCSAdapter
from src.sfcs_cli import main

SN = 'DEMO-SERVER-001'
STATION = 'SAT-DIMM-01'

@pytest.fixture
def setup(tmp_path):
    return ResultStore(tmp_path/'local.db'), MockSFCSAdapter(tmp_path/'remote.db')


def run(setup, scenario='healthy', parent=None, station=STATION):
    store, adapter = setup
    cfg = load_config()
    cfg['execution']['mock_scenario'] = scenario
    return execute(cfg, MockConnection(scenario), adapter, station, store, parent)


@pytest.mark.parametrize('scenario,diagnosis,result', [('healthy','PASS','PASS'),('corrected_error','FAIL','FAIL'),('uncorrected_error','FAIL','FAIL'),('unavailable','UNKNOWN','FAIL'),('sensor_unsupported','WARNING','FAIL')])
def test_results(setup, scenario, diagnosis, result):
    store, adapter = setup
    record = run(setup, scenario)
    assert record['diagnostic_result'] == diagnosis
    assert record['result'] == result
    assert record['server_pn'] and record['test_version'] and record['timestamp']
    assert Delivery(store).submit(adapter, record) == 'sent'
    assert adapter.get_test_history(SN) == [record]


@pytest.mark.parametrize('case', ['station','stage','unknown','offline'])
def test_gate_prevents_collection(setup, case):
    store, adapter = setup
    cfg = load_config()
    if case == 'stage': cfg['server']['test_stage'] = 'IST'
    if case == 'unknown': cfg['server']['serial_number'] = 'UNKNOWN'
    if case == 'offline': adapter.offline = True
    class Never:
        def collect(self, source): pytest.fail('must gate before collection')
    with pytest.raises(SFCSError):
        execute(cfg, Never(), adapter, 'INVALID' if case == 'station' else STATION, store)
    assert store.history(SN) == []


def test_offline_restart_and_duplicates(setup, caplog):
    store, adapter = setup
    result = run(setup)
    adapter.offline = True
    with caplog.at_level('INFO'):
        assert Delivery(store).submit(adapter, result, max_attempts=2, backoff=0) == 'pending'
    with store.connect() as db:
        assert db.execute('SELECT attempts FROM delivery').fetchone()[0] == 2
    adapter.offline = False
    restarted = ResultStore(store.path)
    assert Delivery(restarted).retry(adapter) == {result['run_id']: 'sent'}
    assert Delivery(restarted).submit(adapter, result) == 'sent'
    adapter.upload_result(result)
    assert len(adapter.get_test_history(SN)) == 1
    with pytest.raises(ConflictError): adapter.upload_result({**result, 'result': 'FAIL'})
    with pytest.raises(ConflictError): restarted.save({**result, 'result': 'FAIL'})
    assert json.loads(caplog.records[0].message)['event'] == 'upload_pending'


def test_crash_between_save_and_queue(setup):
    result = run(setup)
    assert Delivery(setup[0]).retry(setup[1]) == {result['run_id']: 'sent'}


def test_retests(setup):
    first = run(setup, 'corrected_error')
    second = run(setup, 'uncorrected_error', first['run_id'])
    third = run(setup, 'healthy', second['run_id'])
    assert len({r['run_id'] for r in (first, second, third)}) == 3
    assert third['execution_type'] == 'RETEST'
    assert setup[0].history(SN) == [first, second, third]
    Delivery(setup[0]).retry(setup[1])
    assert setup[1].get_test_history(SN) == [first, second, third]
    with pytest.raises(SFCSError): run(setup, parent='missing')


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        code = 200
        body = None
        received = []
        def log_message(self, *args): pass
        def handle_request(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length']))) if self.headers.get('Content-Length') else None
            self.received.append((self.path, dict(self.headers), payload))
            value = self.body
            if value is None:
                value = ({'run_id': payload['run_id'], 'accepted': True} if self.path == '/results' else
                         {'eligible': True} if self.path == '/station-validation' else
                         [] if self.path.endswith('/history') else {'serial_number': SN, 'part_number': 'SYNTHETIC', 'stage': 'SAT'})
            self.send_response(self.code)
            self.end_headers()
            self.wfile.write(value if isinstance(value, bytes) else json.dumps(value).encode())
        do_GET = handle_request
        do_POST = handle_request
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{httpd.server_port}', Handler
    httpd.shutdown()
    httpd.server_close()
    thread.join()


def test_rest_end_to_end(server, tmp_path, monkeypatch):
    url, handler = server
    monkeypatch.setenv('TEST_SFCS_TOKEN', 'synthetic-secret')
    adapter = RestSFCSAdapter(url, token_env='TEST_SFCS_TOKEN')
    store = ResultStore(tmp_path/'local.db')
    result = execute(load_config(), MockConnection('healthy'), adapter, STATION, store)
    assert Delivery(store).submit(adapter, result) == 'sent'
    assert adapter.get_test_history(SN) == []
    upload = next(item for item in handler.received if item[0] == '/results')
    assert upload[1]['Idempotency-Key'] == result['run_id']
    assert upload[1]['Authorization'] == 'Bearer synthetic-secret'
    assert 'synthetic-secret' not in json.dumps(store.history(SN))


@pytest.mark.parametrize('code,error', [(401,SFCSError),(403,SFCSError),(409,ConflictError),(429,RetryableError),(500,RetryableError),(408,RetryableError),(302,SFCSError)])
def test_rest_errors(server, code, error):
    url, handler = server
    handler.code, handler.body = code, b'synthetic-secret'
    with pytest.raises(error) as exc: RestSFCSAdapter(url).get_unit(SN)
    assert 'synthetic-secret' not in str(exc.value)


@pytest.mark.parametrize('body', [b'not-json', b'[]', b'null'])
def test_rest_invalid(server, body):
    url, handler = server
    handler.body = body
    with pytest.raises(SFCSError): RestSFCSAdapter(url).get_unit(SN)


def test_timeout_and_auth(monkeypatch):
    adapter = RestSFCSAdapter('http://localhost', timeout=0.01)
    def timeout(*args, **kwargs): raise TimeoutError('synthetic-secret')
    monkeypatch.setattr(adapter.opener, 'open', timeout)
    with pytest.raises(RetryableError): adapter.get_unit(SN)
    monkeypatch.delenv('NO_SUCH_TOKEN', raising=False)
    with pytest.raises(SFCSError): RestSFCSAdapter('http://localhost', token_env='NO_SUCH_TOKEN').get_unit(SN)


@pytest.mark.parametrize('url', ['http://example.com','https://u:p@example.com','file:///tmp/data'])
def test_invalid_url(url):
    with pytest.raises(ValueError): RestSFCSAdapter(url)


def test_rejection_not_retried(setup):
    record = run(setup)
    class Reject:
        def upload_result(self, result): raise SFCSError('rejected')
    delivery = Delivery(setup[0])
    assert delivery.submit(Reject(), record) == 'rejected'
    assert delivery.retry(Reject()) == {}


def test_cli(tmp_path, capsys):
    config = {'adapter':'mock','hardware_config':str(__import__('pathlib').Path('config/test_env.yaml').resolve()),
              'database':'local.db','mock_database':'remote.db'}
    path = tmp_path/'config.yaml'
    path.write_text(yaml.safe_dump(config))
    common = ['--config',str(path)]
    assert main(common + ['run','--serial-number',SN,'--stage','SAT','--station',STATION]) == 0
    result = json.loads(capsys.readouterr().out)
    assert main(common + ['run','--serial-number',SN,'--stage','SAT','--station',STATION,
                          '--scenario','corrected_error','--retest-of',result['run_id']]) == 2
    capsys.readouterr()
    assert main(common + ['history','--serial-number',SN]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 2
    assert main(common + ['retry']) == 0


def test_connection_refused():
    import socket
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        url = f'http://127.0.0.1:{sock.getsockname()[1]}'
    with pytest.raises(RetryableError): RestSFCSAdapter(url, timeout=0.1).get_unit(SN)


def test_invalid_acknowledgement(setup):
    result = run(setup)
    class WrongReceipt:
        def upload_result(self, result): return {'accepted': True, 'run_id': 'wrong'}
    assert Delivery(setup[0]).submit(WrongReceipt(), result) == 'rejected'


def test_rest_offline_queue(server, setup):
    url, handler = server
    result = run(setup)
    adapter = RestSFCSAdapter(url)
    handler.code = 503
    delivery = Delivery(setup[0])
    assert delivery.submit(adapter, result, max_attempts=1) == 'pending'
    handler.code = 200
    assert Delivery(setup[0]).retry(adapter) == {result['run_id']: 'sent'}
