import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from beda.models import (
    Action,
    AuditEvent,
    CRMRecord,
    Enquiry,
    MatchCandidate,
    Proposal,
    Recommendation,
    utc_now_iso,
)


from contextlib import contextmanager


class Database:
    def __init__(self, path: str):
        self.path = path

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self) -> None:
        with self._connection() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS enquiries (
                id TEXT PRIMARY KEY,
                source_message_id TEXT UNIQUE,
                sender TEXT,
                sender_email TEXT,
                sender_name TEXT,
                subject TEXT,
                body TEXT,
                attachment_filename TEXT,
                attachment_content TEXT,
                received_at TEXT,
                status TEXT,
                related_enquiry_id TEXT,
                proposal_json TEXT,
                recommendation_json TEXT,
                draft_response TEXT,
                raw_payload_json TEXT
            );

            CREATE TABLE IF NOT EXISTS match_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enquiry_id TEXT NOT NULL,
                crm_id TEXT NOT NULL,
                company TEXT,
                contact TEXT,
                email TEXT,
                phone TEXT,
                score REAL,
                match_reasons_json TEXT,
                ambiguous INTEGER,
                FOREIGN KEY(enquiry_id) REFERENCES enquiries(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS crm_records (
                id TEXT PRIMARY KEY,
                company TEXT,
                contact TEXT,
                email TEXT,
                phone TEXT,
                location TEXT,
                type TEXT,
                interest TEXT,
                status TEXT
            );

            CREATE TABLE IF NOT EXISTS actions (
                id TEXT PRIMARY KEY,
                enquiry_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                payload_json TEXT,
                status TEXT NOT NULL,
                attempt_count INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 3,
                last_error TEXT,
                result_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(enquiry_id) REFERENCES enquiries(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enquiry_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                details_json TEXT,
                created_at TEXT NOT NULL
            );
            """)

    # --- Enquiry Methods ---

    def create_enquiry(self, enquiry: Enquiry) -> Enquiry:
        proposal_json = enquiry.proposal.model_dump_json() if enquiry.proposal else None
        recommendation_json = enquiry.recommendation.model_dump_json() if enquiry.recommendation else None
        raw_payload_json = json.dumps(enquiry.raw_payload) if enquiry.raw_payload is not None else None

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO enquiries (
                    id, source_message_id, sender, sender_email, sender_name,
                    subject, body, attachment_filename, attachment_content,
                    received_at, status, related_enquiry_id,
                    proposal_json, recommendation_json, draft_response, raw_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    enquiry.id,
                    enquiry.source_message_id,
                    enquiry.sender,
                    enquiry.sender_email,
                    enquiry.sender_name,
                    enquiry.subject,
                    enquiry.body,
                    enquiry.attachment_filename,
                    enquiry.attachment_content,
                    enquiry.received_at,
                    enquiry.status,
                    enquiry.related_enquiry_id,
                    proposal_json,
                    recommendation_json,
                    enquiry.draft_response,
                    raw_payload_json,
                ),
            )

        if enquiry.match_candidates:
            self.save_match_candidates(enquiry.id, enquiry.match_candidates)

        return enquiry

    def update_enquiry(self, enquiry: Enquiry) -> Enquiry:
        proposal_json = enquiry.proposal.model_dump_json() if enquiry.proposal else None
        recommendation_json = enquiry.recommendation.model_dump_json() if enquiry.recommendation else None
        raw_payload_json = json.dumps(enquiry.raw_payload) if enquiry.raw_payload is not None else None

        with self._connection() as conn:
            conn.execute(
                """
                UPDATE enquiries SET
                    source_message_id = ?,
                    sender = ?,
                    sender_email = ?,
                    sender_name = ?,
                    subject = ?,
                    body = ?,
                    attachment_filename = ?,
                    attachment_content = ?,
                    received_at = ?,
                    status = ?,
                    related_enquiry_id = ?,
                    proposal_json = ?,
                    recommendation_json = ?,
                    draft_response = ?,
                    raw_payload_json = ?
                WHERE id = ?
                """,
                (
                    enquiry.source_message_id,
                    enquiry.sender,
                    enquiry.sender_email,
                    enquiry.sender_name,
                    enquiry.subject,
                    enquiry.body,
                    enquiry.attachment_filename,
                    enquiry.attachment_content,
                    enquiry.received_at,
                    enquiry.status,
                    enquiry.related_enquiry_id,
                    proposal_json,
                    recommendation_json,
                    enquiry.draft_response,
                    raw_payload_json,
                    enquiry.id,
                ),
            )

        if enquiry.match_candidates:
            self.save_match_candidates(enquiry.id, enquiry.match_candidates)

        return enquiry

    def _row_to_enquiry(self, row: sqlite3.Row) -> Enquiry:
        proposal = Proposal.model_validate_json(row["proposal_json"]) if row["proposal_json"] else None
        recommendation = (
            Recommendation.model_validate_json(row["recommendation_json"])
            if row["recommendation_json"]
            else None
        )
        raw_payload = json.loads(row["raw_payload_json"]) if row["raw_payload_json"] else None
        candidates = self.get_match_candidates(row["id"])

        return Enquiry(
            id=row["id"],
            source_message_id=row["source_message_id"],
            sender=row["sender"],
            sender_email=row["sender_email"],
            sender_name=row["sender_name"],
            subject=row["subject"] or "",
            body=row["body"] or "",
            attachment_filename=row["attachment_filename"],
            attachment_content=row["attachment_content"],
            received_at=row["received_at"],
            status=row["status"],
            related_enquiry_id=row["related_enquiry_id"],
            proposal=proposal,
            match_candidates=candidates,
            recommendation=recommendation,
            draft_response=row["draft_response"],
            raw_payload=raw_payload,
        )

    def get_enquiry(self, enquiry_id: str) -> Optional[Enquiry]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM enquiries WHERE id = ?", (enquiry_id,)).fetchone()
            if not row:
                return None
            return self._row_to_enquiry(row)

    def find_by_source_id(self, source_message_id: str) -> Optional[Enquiry]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM enquiries WHERE source_message_id = ?", (source_message_id,)).fetchone()
            if not row:
                return None
            return self._row_to_enquiry(row)

    def list_enquiries(self) -> List[Enquiry]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM enquiries ORDER BY id ASC").fetchall()
            return [self._row_to_enquiry(row) for row in rows]

    # --- Match Candidates ---

    def save_match_candidates(self, enquiry_id: str, candidates: List[MatchCandidate]) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM match_candidates WHERE enquiry_id = ?", (enquiry_id,))
            for c in candidates:
                conn.execute(
                    """
                    INSERT INTO match_candidates (
                        enquiry_id, crm_id, company, contact, email, phone,
                        score, match_reasons_json, ambiguous
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        enquiry_id,
                        c.crm_id,
                        c.company,
                        c.contact,
                        c.email,
                        c.phone,
                        c.score,
                        json.dumps(c.match_reasons),
                        1 if c.ambiguous else 0,
                    ),
                )

    def get_match_candidates(self, enquiry_id: str) -> List[MatchCandidate]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM match_candidates WHERE enquiry_id = ? ORDER BY score DESC, crm_id ASC",
                (enquiry_id,),
            ).fetchall()
            return [
                MatchCandidate(
                    crm_id=r["crm_id"],
                    company=r["company"] or "",
                    contact=r["contact"] or "",
                    email=r["email"],
                    phone=r["phone"],
                    score=r["score"],
                    match_reasons=json.loads(r["match_reasons_json"] or "[]"),
                    ambiguous=bool(r["ambiguous"]),
                )
                for r in rows
            ]

    # --- CRM Records ---

    def upsert_crm_record(self, record: CRMRecord) -> CRMRecord:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO crm_records (id, company, contact, email, phone, location, type, interest, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    company=excluded.company,
                    contact=excluded.contact,
                    email=excluded.email,
                    phone=excluded.phone,
                    location=excluded.location,
                    type=excluded.type,
                    interest=excluded.interest,
                    status=excluded.status
                """,
                (
                    record.id,
                    record.company,
                    record.contact,
                    record.email,
                    record.phone,
                    record.location,
                    record.type,
                    record.interest,
                    record.status,
                ),
            )
        return record

    def get_crm_record(self, crm_id: str) -> Optional[CRMRecord]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM crm_records WHERE id = ?", (crm_id,)).fetchone()
            if not row:
                return None
            return CRMRecord(
                id=row["id"],
                company=row["company"],
                contact=row["contact"],
                email=row["email"] or "",
                phone=row["phone"] or "",
                location=row["location"] or "",
                type=row["type"] or "",
                interest=row["interest"] or "",
                status=row["status"] or "",
            )

    def list_crm_records(self) -> List[CRMRecord]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM crm_records ORDER BY id ASC").fetchall()
            return [
                CRMRecord(
                    id=r["id"],
                    company=r["company"],
                    contact=r["contact"],
                    email=r["email"] or "",
                    phone=r["phone"] or "",
                    location=r["location"] or "",
                    type=r["type"] or "",
                    interest=r["interest"] or "",
                    status=r["status"] or "",
                )
                for r in rows
            ]

    # --- Actions ---

    def create_action(self, action: Action) -> Action:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO actions (
                    id, enquiry_id, action_type, idempotency_key, payload_json,
                    status, attempt_count, max_attempts, last_error, result_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action.id,
                    action.enquiry_id,
                    action.action_type,
                    action.idempotency_key,
                    json.dumps(action.payload),
                    action.status,
                    action.attempt_count,
                    action.max_attempts,
                    action.last_error,
                    json.dumps(action.result) if action.result is not None else None,
                    action.created_at,
                    action.updated_at,
                ),
            )
        return action

    def update_action(self, action: Action) -> Action:
        action.updated_at = utc_now_iso()
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE actions SET
                    status = ?,
                    attempt_count = ?,
                    max_attempts = ?,
                    last_error = ?,
                    result_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    action.status,
                    action.attempt_count,
                    action.max_attempts,
                    action.last_error,
                    json.dumps(action.result) if action.result is not None else None,
                    action.updated_at,
                    action.id,
                ),
            )
        return action

    def get_action(self, action_id: str) -> Optional[Action]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
            if not row:
                return None
            return self._row_to_action(row)

    def get_action_by_idempotency_key(self, key: str) -> Optional[Action]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM actions WHERE idempotency_key = ?", (key,)).fetchone()
            if not row:
                return None
            return self._row_to_action(row)

    def list_actions_for_enquiry(self, enquiry_id: str) -> List[Action]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM actions WHERE enquiry_id = ? ORDER BY created_at ASC", (enquiry_id,)).fetchall()
            return [self._row_to_action(r) for r in rows]

    def list_pending_actions(self) -> List[Action]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM actions WHERE status IN ('PENDING', 'FAILED_RETRYABLE') ORDER BY created_at ASC"
            ).fetchall()
            return [self._row_to_action(r) for r in rows]

    def _row_to_action(self, row: sqlite3.Row) -> Action:
        return Action(
            id=row["id"],
            enquiry_id=row["enquiry_id"],
            action_type=row["action_type"],
            idempotency_key=row["idempotency_key"],
            payload=json.loads(row["payload_json"] or "{}"),
            status=row["status"],
            attempt_count=row["attempt_count"],
            max_attempts=row["max_attempts"],
            last_error=row["last_error"],
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # --- Audit Events ---

    def add_audit(
        self, enquiry_id: str, event_type: str, actor: str, details: Optional[Dict[str, Any]] = None
    ) -> AuditEvent:
        event = AuditEvent(
            enquiry_id=enquiry_id,
            event_type=event_type,
            actor=actor,
            details=details or {},
            created_at=utc_now_iso(),
        )
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO audit_events (enquiry_id, event_type, actor, details_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.enquiry_id,
                    event.event_type,
                    event.actor,
                    json.dumps(event.details),
                    event.created_at,
                ),
            )
            event.id = cursor.lastrowid
        return event

    def list_audit(self, enquiry_id: Optional[str] = None) -> List[AuditEvent]:
        with self._connection() as conn:
            if enquiry_id:
                rows = conn.execute(
                    "SELECT * FROM audit_events WHERE enquiry_id = ? ORDER BY id ASC", (enquiry_id,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM audit_events ORDER BY id ASC").fetchall()

            return [
                AuditEvent(
                    id=r["id"],
                    enquiry_id=r["enquiry_id"],
                    event_type=r["event_type"],
                    actor=r["actor"],
                    details=json.loads(r["details_json"] or "{}"),
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    # --- Retention Cleanup ---

    def cleanup_raw_content(self, older_than_days: int) -> int:
        """
        Applies configurable raw-content retention period:
        Redacts raw body, attachment_content, and raw_payload_json while preserving
        metadata and de-identified audit metadata.
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        with self._connection() as conn:
            cursor = conn.execute(
                """
                UPDATE enquiries
                SET body = '[REDACTED_BY_RETENTION_POLICY]',
                    attachment_content = NULL,
                    raw_payload_json = json_set(raw_payload_json, '$.body', '[REDACTED]', '$.attachment_content', '[REDACTED]')
                WHERE received_at < ?
                  AND (body != '[REDACTED_BY_RETENTION_POLICY]' OR attachment_content IS NOT NULL)
                """,
                (cutoff,),
            )
            return cursor.rowcount
