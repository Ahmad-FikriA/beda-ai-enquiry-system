"""Recoverable local quarantine. No mailbox, CRM write, or deletion capability."""
import json
from beda.actions import compute_idempotency_key
from beda.models import Action, Recommendation, utc_now_iso


class Junk:
    def __init__(self, db, runs):
        self.db, self.runs = db, runs

    def was_restored(self, eid):
        with self.db._connection() as conn:
            return conn.execute("SELECT 1 FROM audit_events WHERE enquiry_id=? AND event_type='JUNK_RESTORED' LIMIT 1",(eid,)).fetchone() is not None

    @staticmethod
    def _action(conn, action):
        conn.execute('''INSERT INTO actions
            (id,enquiry_id,action_type,idempotency_key,payload_json,status,attempt_count,result_json,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)''',
            (action.id,action.enquiry_id,action.action_type,action.idempotency_key,json.dumps(action.payload),
             action.status,action.attempt_count,json.dumps(action.result),action.created_at,action.updated_at))

    @staticmethod
    def _event(conn, eid, version, event, actor, details):
        conn.execute('INSERT INTO audit_events(enquiry_id,event_type,actor,details_json,created_at) VALUES(?,?,?,?,?)',
                     (eid,event,actor,json.dumps({**details,'run_version':version}),utc_now_iso()))

    def move(self, eq, version, automatic, pending_action=None):
        actor='junk_policy' if automatic else 'local_reviewer'
        result={'mode':'local_quarantine','folder':'junk','recoverable':True,'permanently_deleted':False,
                'crm_modified':False,'external_message_sent':False,'automatic':automatic}
        with self.db._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            current=conn.execute('SELECT MAX(version) FROM runs WHERE enquiry_id=?',(eq.id,)).fetchone()[0]
            expected='PROCESSING' if automatic else 'PENDING_APPROVAL'
            row=conn.execute('SELECT status FROM enquiries WHERE id=?',(eq.id,)).fetchone()
            if current!=version or not row or row['status']!=expected:
                raise ValueError('This run has changed. Open its latest version.')
            eq.status='JUNK'
            eq.draft_response=None
            if automatic:
                self._action(conn,Action(id=f'LIVE-{eq.id}-v{version}',enquiry_id=eq.id,action_type='MOVE_TO_JUNK',
                    idempotency_key=compute_idempotency_key(eq.id,'MOVE_TO_JUNK',f'live-v{version}'),
                    payload={'mode':'local_quarantine','run_version':version},status='SUCCEEDED',attempt_count=1,result=result))
            else:
                if not pending_action:
                    raise ValueError('A pending junk review is required')
                changed=conn.execute("UPDATE actions SET status='SUCCEEDED',attempt_count=1,result_json=?,updated_at=? WHERE id=? AND status='PENDING_APPROVAL' AND action_type='REVIEW_JUNK'",
                    (json.dumps(result),utc_now_iso(),pending_action.id)).rowcount
                if not changed:
                    raise ValueError('This junk review has already been handled')
                self._event(conn,eq.id,version,'APPROVED',actor,{'stage':'approval','action_id':pending_action.id,
                    'message':'Reviewer approved moving this message to the recoverable local Junk folder.'})
            conn.execute('UPDATE enquiries SET status=?,proposal_json=?,recommendation_json=?,draft_response=NULL WHERE id=?',
                         (eq.status,eq.proposal.model_dump_json(),eq.recommendation.model_dump_json(),eq.id))
            self._event(conn,eq.id,version,'JUNK_QUARANTINED',actor,{'stage':'junk',**result,
                'reason':eq.proposal.rationale,'message':'Moved to local Junk. No reply, CRM change or permanent deletion. You can restore it.'})
            self._event(conn,eq.id,version,'JUNK_AUDITED',actor,{'stage':'audit',
                'message':'Junk decision recorded. Original message and run history retained.'})
            conn.execute('UPDATE runs SET snapshot_json=? WHERE enquiry_id=? AND version=?',(eq.model_dump_json(),eq.id,version))
        return eq

    def restore(self, eid, version):
        if type(version) is not int:
            raise ValueError('Current run version is required')
        eq=self.db.get_enquiry(eid)
        if not eq or not (eq.status=='JUNK' or (eq.status=='PENDING_APPROVAL' and eq.recommendation and eq.recommendation.action=='REVIEW_JUNK')):
            raise ValueError('Only quarantined messages or pending junk reviews can be restored')
        with self.db._connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            current=conn.execute('SELECT MAX(version) FROM runs WHERE enquiry_id=?',(eid,)).fetchone()[0]
            status=conn.execute('SELECT status FROM enquiries WHERE id=?',(eid,)).fetchone()[0]
            if version!=current or status!=eq.status:
                raise ValueError('This run has changed. Open its latest version.')
            conn.execute('UPDATE runs SET snapshot_json=? WHERE enquiry_id=? AND version=?',(eq.model_dump_json(),eid,version))
            next_version=version+1
            eq.status='PENDING_APPROVAL'
            eq.draft_response=None
            eq.recommendation=Recommendation(action='REVIEW_RESTORED_ENQUIRY',owner=eq.recommendation.owner,
                confidence='LOW',requires_approval=True,
                explanation='A reviewer marked this message as not junk. Review the original input or start a new full run; automatic quarantine is disabled for this enquiry.')
            conn.execute('INSERT INTO runs VALUES(?,?,?,?,?,?)',(eid,next_version,'restore',None,utc_now_iso(),eq.model_dump_json()))
            conn.execute("UPDATE actions SET status='SUPERSEDED' WHERE enquiry_id=? AND status='PENDING_APPROVAL'",(eid,))
            conn.execute('UPDATE enquiries SET status=?,recommendation_json=?,draft_response=NULL WHERE id=?',
                         (eq.status,eq.recommendation.model_dump_json(),eid))
            self._action(conn,Action(id=f'LIVE-{eid}-v{next_version}',enquiry_id=eid,action_type='REVIEW_RESTORED_ENQUIRY',
                idempotency_key=compute_idempotency_key(eid,'REVIEW_RESTORED_ENQUIRY',f'live-v{next_version}'),
                payload={'mode':'local_review_only','run_version':next_version,'owner':eq.recommendation.owner}))
            self._event(conn,eid,next_version,'JUNK_RESTORED','local_reviewer',{'stage':'junk','previous_version':version,
                'message':'Marked not junk and restored to Inbox. Original AI classification is retained; future junk classifications require human review.'})
            self._event(conn,eid,next_version,'APPROVAL_REQUESTED','local_reviewer',{'stage':'approval',
                'message':'Restored message awaits human review. No reply was generated or sent.'})
        return eq
