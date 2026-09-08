"""Durable local intake. One worker per database; model outages require human retry."""
import json
import re
from threading import Event, Thread
from beda.models import Enquiry, Recommendation, utc_now_iso


class WorkQueue:
    def __init__(self, service):
        self.service, self.db = service, service.db
        self.stopping = Event()
        self.thread = None
        with self.db._connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS work_items (
                    id INTEGER PRIMARY KEY, enquiry_id TEXT NOT NULL,
                    token TEXT UNIQUE NOT NULL, mode TEXT NOT NULL,
                    payload_json TEXT NOT NULL, state TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0, baseline_version INTEGER NOT NULL,
                    last_error TEXT, review_note TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_work ON work_items(enquiry_id)
                    WHERE state IN ('QUEUED','RUNNING','NEEDS_HUMAN_REVIEW');
                CREATE TABLE IF NOT EXISTS queue_control (id INTEGER PRIMARY KEY CHECK(id=1),
                    paused INTEGER NOT NULL, error TEXT);
                INSERT OR IGNORE INTO queue_control VALUES (1,0,NULL);
            """)

    def items(self):
        with self.db._connection() as conn:
            return [dict(r) for r in conn.execute('SELECT * FROM work_items ORDER BY id')]

    def latest(self, eid):
        with self.db._connection() as conn:
            row = conn.execute('SELECT * FROM work_items WHERE enquiry_id=? ORDER BY id DESC LIMIT 1', (eid,)).fetchone()
            return dict(row) if row else None

    def health(self):
        with self.db._connection() as conn:
            row = conn.execute('SELECT * FROM queue_control WHERE id=1').fetchone()
            return {'paused': bool(row['paused']), 'error': row['error']}

    def audit(self, conn, job, event, message):
        conn.execute('INSERT INTO audit_events(enquiry_id,event_type,actor,details_json,created_at) VALUES (?,?,?,?,?)',
                     (job['enquiry_id'], event, 'work_queue', json.dumps({'queue_job_id': job['id'],
                      'message': message, 'stage': 'failure' if 'REVIEW' in event else 'input'}), utc_now_iso()))

    @staticmethod
    def normalize(payload):
        if not isinstance(payload, dict):
            raise ValueError('Expected an enquiry object')
        payload = dict(payload)
        eid = payload.get('id') or payload.get('source_message_id')
        if not isinstance(eid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', eid):
            raise ValueError('ID must contain 1–80 letters, digits, underscores or hyphens')
        if payload.get('source_message_id', eid) != eid:
            raise ValueError('Source ID and enquiry ID disagree')
        payload['id'] = eid
        for field in ('from', 'subject', 'body', 'attachment_content', 'attachment_filename'):
            if payload.get(field) is not None and not isinstance(payload[field], str):
                raise ValueError(f'{field} must be text')
        for field in ('from', 'subject', 'body'):
            payload[field] = (payload.get(field) or '').strip()
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
        if len(encoded.encode()) > 100000:
            raise ValueError('Enquiry exceeds 100 KB')
        return payload, encoded

    def submit(self, payload, mode='initial', request_id=None):
        payload, encoded = self.normalize(payload)
        eid = payload['id']
        if mode not in ('initial', 'full', 'draft'):
            raise ValueError('Invalid run mode')
        if mode != 'initial' and (not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', request_id)):
            raise ValueError('A unique request ID is required')
        token = 'source:' + eid if mode == 'initial' else 'rerun:' + request_id
        with self.db._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            old = conn.execute('SELECT * FROM work_items WHERE token=?', (token,)).fetchone()
            if old:
                if old['enquiry_id'] != eid or old['mode'] != mode or (mode == 'initial' and old['payload_json'] != encoded):
                    raise ValueError('ID already accepted with different input; use a new full run')
                return {'id': eid, 'status': old['state'], 'job_id': old['id']}
            if conn.execute("SELECT 1 FROM work_items WHERE enquiry_id=? AND state IN ('QUEUED','RUNNING','NEEDS_HUMAN_REVIEW')", (eid,)).fetchone():
                raise ValueError('Existing work must be retried or manually reviewed first')
            eq = self.db.get_enquiry(eid)
            if mode == 'initial' and eq:
                original = eq.raw_payload or {'id': eid, 'from': eq.sender, 'subject': eq.subject, 'body': eq.body,
                                             'attachment_content': eq.attachment_content, 'attachment_filename': eq.attachment_filename}
                normalized, _ = self.normalize(original)
                if any(normalized.get(key) != payload.get(key) for key in normalized.keys() | payload.keys()):
                    raise ValueError('Existing enquiry differs; use a new full run')
                return {'id': eid, 'status': eq.status}
            if mode != 'initial':
                if not eq or eq.status == 'PROCESSING':
                    raise ValueError('A finished enquiry is required')
                if mode == 'draft' and (not eq.proposal or not eq.recommendation or eq.proposal.category == 'junk'):
                    raise ValueError('A validated non-junk proposal is required')
                payload = dict(eq.raw_payload or {'id': eid, 'from': eq.sender, 'subject': eq.subject, 'body': eq.body})
                if mode == 'full':
                    payload = self.service.documents.attach(payload)
                payload, encoded = self.normalize(payload)
            paused = conn.execute('SELECT paused FROM queue_control WHERE id=1').fetchone()[0]
            state = 'NEEDS_HUMAN_REVIEW' if paused else 'QUEUED'
            now = utc_now_iso()
            cursor = conn.execute('INSERT INTO work_items(enquiry_id,token,mode,payload_json,state,baseline_version,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                                  (eid, token, mode, encoded, state, self.service.runs.current(eid), now, now))
            job = {'id': cursor.lastrowid, 'enquiry_id': eid}
            self.audit(conn, job, 'QUEUE_ACCEPTED', 'Validated source saved durably before interpretation.')
            if paused:
                self.audit(conn, job, 'QUEUE_HUMAN_REVIEW', 'Model processing is paused. Review source or explicitly retry.')
            return {'id': eid, 'status': state, 'job_id': job['id']}

    def transition(self, eid, note=None):
        with self.db._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            job = conn.execute('SELECT * FROM work_items WHERE enquiry_id=? ORDER BY id DESC LIMIT 1', (eid,)).fetchone()
            if job and note is None and job['state'] in ('QUEUED', 'RUNNING'):
                return {'id': eid, 'status': job['state']}
            if not job or job['state'] != 'NEEDS_HUMAN_REVIEW':
                raise ValueError('This item is not awaiting manual review')
            state = 'QUEUED' if note is None else 'HUMAN_REVIEWED'
            conn.execute('UPDATE work_items SET state=?,review_note=?,updated_at=? WHERE id=?', (state, note, utc_now_iso(), job['id']))
            self.audit(conn, job, 'QUEUE_RETRY_REQUESTED' if note is None else 'QUEUE_MANUALLY_REVIEWED', note or 'Reviewer requested one bounded model retry.')
            return {'id': eid, 'status': state}

    def retry(self, eid):
        return self.transition(eid)

    def review(self, eid, note):
        if not isinstance(note, str) or not note.strip() or len(note) > 2000:
            raise ValueError('Provide a review note between 1 and 2000 characters')
        return self.transition(eid, note.strip())

    def pause(self, conn, message):
        conn.execute('UPDATE queue_control SET paused=1,error=? WHERE id=1', (message,))
        for job in conn.execute("SELECT * FROM work_items WHERE state IN ('RUNNING','QUEUED')").fetchall():
            conn.execute("UPDATE work_items SET state='NEEDS_HUMAN_REVIEW',last_error=?,updated_at=? WHERE id=?", (message, utc_now_iso(), job['id']))
            self.audit(conn, job, 'QUEUE_HUMAN_REVIEW', message)

    def work_once(self):
        with self.db._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            job = conn.execute("SELECT * FROM work_items WHERE state='QUEUED' ORDER BY id LIMIT 1").fetchone()
            if not job:
                return False
            job = dict(job)
            conn.execute("UPDATE work_items SET state='RUNNING',attempts=attempts+1,updated_at=? WHERE id=?", (utc_now_iso(), job['id']))
            self.audit(conn, job, 'QUEUE_STARTED', 'Saved work claimed by the local worker.')
        try:
            eq = self.service.process_input(json.loads(job['payload_json']), force=True,
                draft_only=job['mode'] == 'draft', request_id=f"queue-{job['id']}-attempt-{job['attempts'] + 1}")
            failed = eq.status == 'MODEL_FAILED'
        except Exception:
            # Never expose arbitrary exception text (which may contain credentials).
            failed = True
        with self.db._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if failed:
                self.pause(conn, 'Interpretation unavailable or interrupted. Source is saved; human review required. Fix the provider/configuration, then explicitly retry.')
            else:
                conn.execute("UPDATE work_items SET state='DONE',last_error=NULL,updated_at=? WHERE id=?", (utc_now_iso(), job['id']))
                conn.execute('UPDATE queue_control SET paused=0,error=NULL WHERE id=1')
                self.audit(conn, job, 'QUEUE_DONE', 'Interpretation completed; normal approval rules still apply.')
        return True

    def recover(self):
        with self.db._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            interrupted = False
            for job in conn.execute("SELECT * FROM work_items WHERE state='RUNNING'").fetchall():
                eq = self.db.get_enquiry(job['enquiry_id'])
                version = self.service.runs.current(job['enquiry_id'])
                run = conn.execute('SELECT * FROM runs WHERE enquiry_id=? AND version=?', (job['enquiry_id'], version)).fetchone()
                snapshot = json.loads(run['snapshot_json']) if run and run['snapshot_json'] else None
                completed = snapshot and snapshot['status'] in ('PENDING_APPROVAL', 'COMPLETED', 'JUNK', 'REJECTED')
                # A version row alone is only a start marker, not completion evidence.
                token_matches = run and run['request_id'] == f"queue-{job['id']}-attempt-{job['attempts']}"
                action_present = snapshot and (snapshot['status'] == 'JUNK' or conn.execute(
                    'SELECT 1 FROM actions WHERE id=?', (f"LIVE-{job['enquiry_id']}-v{version}",)).fetchone())
                if eq and version > job['baseline_version'] and token_matches and completed and action_present:
                    conn.execute("UPDATE work_items SET state='DONE',updated_at=? WHERE id=?", (utc_now_iso(), job['id']))
                    self.audit(conn, job, 'QUEUE_RECOVERED', 'Completed result recovered without replay.')
                else:
                    interrupted = True
            if interrupted:
                self.pause(conn, 'Worker interrupted. Source preserved; reviewer must check and explicitly retry.')

    def enquiry(self, eid):
        eq, job = self.db.get_enquiry(eid), self.latest(eid)
        if not job or job['state'] == 'DONE':
            return eq
        payload = json.loads(job['payload_json'])
        eq = eq or Enquiry(id=eid, source_message_id=eid, sender=payload['from'], subject=payload['subject'],
                          body=payload['body'], raw_payload=payload, attachment_content=payload.get('attachment_content'))
        eq.status = 'PROCESSING' if job['state'] == 'RUNNING' else job['state']
        if job['state'] in ('NEEDS_HUMAN_REVIEW', 'HUMAN_REVIEWED'):
            eq.draft_response = None
            eq.recommendation = Recommendation(action='MANUAL_INTERPRETATION', owner='Ties Rahardjo', confidence='LOW',
                explanation=job['review_note'] or job['last_error'] or 'Model processing paused. Review original source or explicitly retry.')
        return eq

    def start(self):
        self.recover()
        def loop():
            while not self.stopping.is_set():
                try:
                    if self.work_once():
                        continue
                except Exception:
                    # A database failure cannot acknowledge/delete saved work.
                    pass
                self.stopping.wait(.25)
        self.thread = Thread(target=loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stopping.set()
        if self.thread:
            self.thread.join(timeout=1)
