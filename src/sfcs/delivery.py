"""Durable outbox; repeat delivery uses the original immutable Run ID."""
import json
import logging
import time
from . import SFCSError, RetryableError

LOG = logging.getLogger(__name__)


def event(name, **fields):
    LOG.info(json.dumps({'event': name, **fields}, sort_keys=True))


class Delivery:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS delivery (run_id TEXT PRIMARY KEY, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0)')
            db.execute("INSERT OR IGNORE INTO delivery SELECT run_id, 'pending', 0 FROM results")

    def submit(self, adapter, result, max_attempts=3, backoff=0.25):
        if type(max_attempts) is not int or not 1 <= max_attempts <= 10:
            raise ValueError('max_attempts must be 1..10')
        if not isinstance(backoff, (int, float)) or not 0 <= backoff <= 5:
            raise ValueError('backoff must be 0..5 seconds')
        self.store.save(result)
        run_id = result['run_id']
        with self.store.connect() as db:
            db.execute("INSERT OR IGNORE INTO delivery VALUES (?, 'pending', 0)", (run_id,))
            status = db.execute('SELECT status FROM delivery WHERE run_id=?', (run_id,)).fetchone()[0]
        if status in ('sent', 'rejected'):
            return status
        for attempt in range(max_attempts):
            with self.store.connect() as db:
                db.execute('UPDATE delivery SET attempts=attempts+1 WHERE run_id=?', (run_id,))
            try:
                receipt = adapter.upload_result(result)
                if receipt.get('accepted') is not True or receipt.get('run_id') != run_id:
                    raise SFCSError('Invalid upload acknowledgement')
            except RetryableError:
                event('upload_pending', run_id=run_id)
                if attempt + 1 < max_attempts:
                    time.sleep(min(backoff * 2**attempt, 5))
                continue
            except SFCSError:
                with self.store.connect() as db:
                    db.execute("UPDATE delivery SET status='rejected' WHERE run_id=?", (run_id,))
                event('upload_rejected', run_id=run_id)
                return 'rejected'
            with self.store.connect() as db:
                db.execute("UPDATE delivery SET status='sent' WHERE run_id=?", (run_id,))
            event('upload_sent', run_id=run_id)
            return 'sent'
        return 'pending'

    def retry(self, adapter, **options):
        with self.store.connect() as db:
            # Recover runs saved just before a process interruption.
            db.execute("INSERT OR IGNORE INTO delivery SELECT run_id, 'pending', 0 FROM results")
            rows = db.execute("SELECT r.payload FROM results r JOIN delivery d USING(run_id) WHERE d.status='pending' ORDER BY r.rowid").fetchall()
        return {r['run_id']: self.submit(adapter, r, **options)
                for r in (json.loads(row[0]) for row in rows)}
