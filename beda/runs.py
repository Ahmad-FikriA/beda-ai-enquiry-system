"""Versioned run snapshots; existing enquiries remain the current-version projection."""
import json
from beda.models import utc_now_iso


class Runs:
    def __init__(self, db):
        self.db = db
        with db._connection() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS runs (
                enquiry_id TEXT NOT NULL, version INTEGER NOT NULL, mode TEXT NOT NULL,
                request_id TEXT UNIQUE, created_at TEXT NOT NULL, snapshot_json TEXT,
                PRIMARY KEY(enquiry_id,version))''')

    def current(self, eid):
        with self.db._connection() as conn:
            return conn.execute('SELECT COALESCE(MAX(version),0) FROM runs WHERE enquiry_id=?',(eid,)).fetchone()[0]

    def seen(self, token):
        if not token:
            return False
        with self.db._connection() as conn:
            return conn.execute('SELECT 1 FROM runs WHERE request_id=?',(token,)).fetchone() is not None

    def begin(self, eid, mode, token=None):
        old = self.db.get_enquiry(eid)
        with self.db._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            version = conn.execute('SELECT COALESCE(MAX(version),0) FROM runs WHERE enquiry_id=?',(eid,)).fetchone()[0]
            if version == 0 and old:
                version = 1
                conn.execute('INSERT INTO runs VALUES(?,?,?,?,?,?)',
                    (eid,1,'legacy',None,old.received_at,old.model_dump_json()))
            elif version and old:
                conn.execute('UPDATE runs SET snapshot_json=? WHERE enquiry_id=? AND version=?',
                             (old.model_dump_json(),eid,version))
            version += 1
            conn.execute('INSERT INTO runs VALUES(?,?,?,?,?,?)',(eid,version,mode,token,utc_now_iso(),None))
            conn.execute("UPDATE actions SET status='SUPERSEDED' WHERE enquiry_id=? AND status='PENDING_APPROVAL'",(eid,))
        return version

    def save(self, eq):
        with self.db._connection() as conn:
            conn.execute('UPDATE runs SET snapshot_json=? WHERE enquiry_id=? AND version=?',
                         (eq.model_dump_json(),eq.id,self.current(eq.id)))

    def list(self, eid):
        with self.db._connection() as conn:
            return [dict(r) for r in conn.execute('SELECT version,mode,created_at FROM runs WHERE enquiry_id=? ORDER BY version DESC',(eid,))]

    def snapshot(self, eid, version):
        with self.db._connection() as conn:
            row=conn.execute('SELECT snapshot_json FROM runs WHERE enquiry_id=? AND version=?',(eid,version)).fetchone()
            return json.loads(row[0]) if row and row[0] else None
