"""Transactional immutable payloads; delivery state is stored separately."""
import json
import sqlite3
from pathlib import Path
from . import ConflictError


class ResultStore:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS results (run_id TEXT PRIMARY KEY, sn TEXT NOT NULL, payload TEXT NOT NULL)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def save(self, result):
        payload = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO results VALUES (?, ?, ?)',
                       (result['run_id'], result['server_sn'], payload))
            existing = db.execute('SELECT payload FROM results WHERE run_id=?', (result['run_id'],)).fetchone()[0]
            if existing != payload:
                raise ConflictError('Run ID payload conflict')
        return result['run_id']

    def history(self, sn):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute(
                'SELECT payload FROM results WHERE sn=? ORDER BY rowid', (sn,))]
