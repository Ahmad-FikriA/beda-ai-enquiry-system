import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from beda.live import LiveService
from beda.llm import ModelError, Gemini, Analysis
from beda.storage import Database
from beda.work_queue import WorkQueue
from tests.test_live import FakeModel


class WorkQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Database(str(Path(self.temp.name)/'queue.db'));self.db.initialize()
        self.service=LiveService(self.db,FakeModel())
        self.queue=WorkQueue(self.service)
        self.payload={'id':'one','from':'Alex <alex@example.com>','subject':' Solar ',
                      'body':'Call 0400 123 456 for solar'}

    def tearDown(self):
        self.queue.stop()
        self.temp.cleanup()

    def fail_model(self):
        return patch.object(self.service.model,'generate',side_effect=ModelError('Provider unavailable'))

    def test_acceptance_persists_normalized_input_without_model_calls(self):
        with self.fail_model() as model:
            receipt=self.queue.submit(self.payload)
            self.assertEqual(receipt['status'],'QUEUED')
            self.assertEqual(model.call_count,0)
        reopened=WorkQueue(LiveService(self.db,FakeModel()))
        self.assertEqual(reopened.enquiry('one').subject,'Solar')
        self.assertEqual(reopened.enquiry('one').body,self.payload['body'])
        self.assertEqual(reopened.latest('one')['state'],'QUEUED')
        self.assertIsNone(reopened.enquiry('one').proposal)

    def test_duplicate_delivery_is_idempotent_but_conflicting_payload_is_rejected(self):
        self.queue.submit(self.payload)
        self.queue.submit(self.payload)
        with self.assertRaises(ValueError):self.queue.submit({**self.payload,'body':'Different work'})
        self.assertEqual(len(self.queue.items()),1)
        self.queue.work_once()
        self.queue.submit(self.payload)
        self.assertEqual(len(self.db.list_actions_for_enquiry('one')),1)
        self.assertEqual(self.service.runs.current('one'),1)

    def test_bad_input_never_reaches_queue_even_during_outage(self):
        for bad in ({'id':'bad id'},{'id':'valid','body':[]},{'id':'valid','body':'x'*100001}):
            with self.assertRaises(ValueError):self.queue.submit(bad)
        self.assertEqual(self.queue.items(),[])

    def test_outage_routes_failed_waiting_and_new_work_to_humans_without_call_storm(self):
        self.queue.submit(self.payload)
        self.queue.submit({**self.payload,'id':'two'})
        with self.fail_model() as model:
            self.assertTrue(self.queue.work_once())
            third=self.queue.submit({**self.payload,'id':'three'})
            self.assertFalse(self.queue.work_once())
            self.assertEqual(model.call_count,1)
        self.assertEqual(third['status'],'NEEDS_HUMAN_REVIEW')
        for eid in ('one','two','three'):
            eq=self.queue.enquiry(eid)
            self.assertEqual(eq.status,'NEEDS_HUMAN_REVIEW')
            self.assertIsNone(eq.proposal)
            self.assertIsNone(eq.draft_response)
            self.assertEqual(eq.recommendation.action,'MANUAL_INTERPRETATION')
            self.assertEqual(self.db.list_actions_for_enquiry(eid),[])

    def test_outage_state_survives_restart_and_explicit_retry_reuses_work(self):
        self.queue.submit(self.payload)
        with self.fail_model():self.queue.work_once()
        reopened=WorkQueue(LiveService(self.db,FakeModel()));reopened.recover()
        self.assertTrue(reopened.health()['paused'])
        self.assertFalse(reopened.work_once())
        reopened.retry('one')
        reopened.retry('one')  # repeated click does not add work
        reopened.work_once()
        self.assertFalse(reopened.health()['paused'])
        self.assertEqual(len(reopened.items()),1)
        self.assertEqual(reopened.enquiry('one').status,'PENDING_APPROVAL')
        self.assertEqual(reopened.latest('one')['attempts'],2)
        self.assertEqual(len(self.db.list_actions_for_enquiry('one')),1)

    def test_manual_review_is_persisted_and_cannot_be_retried(self):
        self.queue.submit(self.payload)
        with self.fail_model():self.queue.work_once()
        with self.assertRaises(ValueError):self.queue.review('one',' ')
        self.queue.review('one','Reviewed source; follow up with customer manually.')
        self.assertEqual(self.queue.enquiry('one').status,'HUMAN_REVIEWED')
        with self.assertRaises(ValueError):self.queue.retry('one')
        self.assertFalse(self.queue.work_once())
        self.assertEqual(self.db.list_actions_for_enquiry('one'),[])
        self.assertIn('QUEUE_MANUALLY_REVIEWED',[e.event_type for e in self.db.list_audit('one')])

    def test_interrupted_claim_is_not_silently_replayed_on_restart(self):
        self.queue.submit(self.payload)
        with self.db._connection() as conn:
            conn.execute("UPDATE work_items SET state='RUNNING', attempts=1")
        self.queue.recover()
        self.assertEqual(self.queue.enquiry('one').status,'NEEDS_HUMAN_REVIEW')
        self.assertFalse(self.queue.work_once())
        self.queue.retry('one');self.queue.work_once()
        self.assertEqual(len(self.db.list_actions_for_enquiry('one')),1)

    def test_completed_pipeline_before_queue_ack_is_reconciled_without_duplicate_action(self):
        self.queue.submit(self.payload)
        with self.db._connection() as conn:
            conn.execute("UPDATE work_items SET state='RUNNING', attempts=1")
        self.service.process_input(self.payload,request_id='queue-1-attempt-1')
        self.queue.recover()
        self.assertEqual(self.queue.latest('one')['state'],'DONE')
        self.assertFalse(self.queue.work_once())
        self.assertEqual(len(self.db.list_actions_for_enquiry('one')),1)

    def test_restart_after_version_started_is_not_a_completed_rerun(self):
        self.queue.submit(self.payload);self.queue.work_once()
        self.queue.submit({'id':'one'},mode='full',request_id='crash-rerun-001')
        job=self.queue.latest('one')
        with self.db._connection() as conn:
            conn.execute("UPDATE work_items SET state='RUNNING',attempts=1 WHERE id=?",(job['id'],))
        self.service.runs.begin('one','full',f"queue-{job['id']}-attempt-1")
        self.queue.recover()
        self.assertEqual(self.queue.latest('one')['state'],'NEEDS_HUMAN_REVIEW')

    def test_legacy_saved_source_conflicts_are_not_acknowledged(self):
        self.service.process_input(self.payload)
        for changes in ({'from':'Different <different@example.com>'},{'attachment_content':'New document'}):
            with self.assertRaises(ValueError):self.queue.submit({**self.payload,**changes})
        self.assertEqual(self.queue.items(),[])

    def test_rerun_request_id_cannot_be_reused_for_another_enquiry(self):
        for eid in ('one','two'):
            self.queue.submit({**self.payload,'id':eid});self.queue.work_once()
        self.queue.submit({'id':'one'},mode='full',request_id='same-request-001')
        with self.assertRaises(ValueError):self.queue.submit({'id':'two'},mode='full',request_id='same-request-001')
        self.queue.submit({'id':'one'},mode='full',request_id='same-request-001')
        self.queue.work_once()
        self.assertEqual(self.service.runs.current('one'),2)
        self.assertEqual(self.service.runs.current('two'),1)

    def test_outage_after_extraction_preserves_facts_without_creating_an_action(self):
        original=self.service.model.generate
        def fail_draft(instruction,data,schema,log):
            if schema is not Analysis:raise ModelError('Provider went offline')
            return original(instruction,data,schema,log)
        self.queue.submit(self.payload)
        with patch.object(self.service.model,'generate',side_effect=fail_draft):self.queue.work_once()
        eq=self.queue.enquiry('one')
        self.assertEqual(eq.status,'NEEDS_HUMAN_REVIEW')
        self.assertEqual(eq.proposal.extracted_fields['phone'],'0400 123 456')
        self.assertIsNone(eq.draft_response)
        self.assertEqual(self.db.list_actions_for_enquiry('one'),[])

    def test_forced_offline_demo_does_not_contact_provider(self):
        with patch.dict('os.environ',{'BEDA_MODEL_OFFLINE':'1','GEMINI_API_KEY':'test-only'}):
            with patch('beda.llm.urlopen') as transport:
                with self.assertRaises(ModelError):Gemini().generate('',{},Analysis,lambda *args:None)
                transport.assert_not_called()

    def test_research_model_outage_stops_before_drafting_and_approval(self):
        from beda.llm import Fact
        def model(instruction,data,schema,log):
            if schema is Analysis:
                return Analysis(category='technical',confidence='HIGH',facts=[Fact(name='phone',value='0400 123 456',evidence='0400 123 456')],
                                missing_fields=[],constraints=[],needs_research=True,rationale='Research needed')
            raise ModelError('Research provider unavailable')
        self.queue.submit(self.payload)
        with patch.object(self.service.model,'generate',side_effect=model) as calls:
            self.queue.work_once()
        self.assertEqual(calls.call_count,2)
        self.assertEqual(self.queue.enquiry('one').status,'NEEDS_HUMAN_REVIEW')
        self.assertEqual(self.db.list_actions_for_enquiry('one'),[])
