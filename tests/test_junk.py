"""Policy tests use controlled model output, not evidence of Gemini quality."""
import tempfile
import unittest
from pathlib import Path
from beda.live import LiveService
from beda.llm import Analysis, Fact, Draft
from beda.models import CRMRecord
from beda.storage import Database


class JunkModel:
    model = 'test-double'
    key = 'test'

    def __init__(self, confidence='HIGH', category='junk', supported=True):
        self.calls = []
        self.confidence, self.category, self.supported = confidence, category, supported

    def generate(self, instruction, data, schema, log):
        self.calls.append((instruction, data, schema))
        if schema is Draft:
            return Draft(text='Thank you for contacting BEDA.')
        return Analysis(category=self.category, confidence=self.confidence,
            facts=[Fact(name='offer', value='bulk leads', evidence='Buy bulk leads' if self.supported else 'Invented source')],
            missing_fields=['company', 'phone'], constraints=[], needs_research=True,
            rationale='Unsolicited advertising unrelated to BEDA services.')


class JunkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.tmp.name)/'test.db'))
        self.db.initialize()
        self.model = JunkModel()
        self.service = LiveService(self.db, self.model)
        self.payload = {'id':'novel-spam-42', 'from':'seller@example.com', 'subject':'Special offer',
                        'body':'Buy bulk leads today. Pay using cryptocurrency.'}

    def tearDown(self):
        self.tmp.cleanup()

    def test_supported_junk_is_recoverably_quarantined_before_missing_information(self):
        eq = self.service.process_input(self.payload)
        self.assertEqual(eq.status, 'JUNK')
        self.assertFalse(eq.recommendation.requires_approval)
        self.assertEqual(eq.body, self.payload['body'])
        self.assertIsNone(eq.draft_response)
        self.assertEqual(len(self.model.calls), 1)
        events = [e.event_type for e in self.db.list_audit(eq.id)]
        self.assertIn('JUNK_QUARANTINED', events)
        self.assertIn('JUNK_AUDITED', events)
        for event in ('INFORMATION_CHECKED','RESEARCH_CHECKED','DRAFTED','APPROVAL_REQUESTED'):
            self.assertNotIn(event, events)
        action = self.db.list_actions_for_enquiry(eq.id)[0]
        self.assertEqual(action.status, 'SUCCEEDED')
        self.assertFalse(action.result['crm_modified'])
        self.assertFalse(action.result['external_message_sent'])
        self.assertFalse(action.result['permanently_deleted'])
        self.assertEqual(self.service.runs.snapshot(eq.id,1)['status'], 'JUNK')

    def test_duplicate_input_does_not_repeat_move_or_call_model(self):
        self.service.process_input(self.payload)
        self.service.process_input(self.payload)
        self.assertEqual(len(self.model.calls),1)
        self.assertEqual(len(self.db.list_actions_for_enquiry(self.payload['id'])),1)
        self.assertEqual(sum(e.event_type=='JUNK_QUARANTINED' for e in self.db.list_audit(self.payload['id'])),1)

    def test_uncertain_or_unsupported_junk_requires_review_without_drafting(self):
        for confidence, supported in [('LOW',True),('MEDIUM',True),('HIGH',False)]:
            with self.subTest(confidence=confidence,supported=supported):
                service=LiveService(self.db,JunkModel(confidence=confidence,supported=supported))
                eq=service.process_input({**self.payload,'id':f'{confidence}-{supported}'})
                self.assertEqual(eq.status,'PENDING_APPROVAL')
                self.assertEqual(eq.recommendation.action,'REVIEW_JUNK')
                self.assertIsNone(eq.draft_response)
                self.assertEqual(len(service.model.calls),1)
                self.assertNotIn('INFORMATION_CHECKED',[e.event_type for e in self.db.list_audit(eq.id)])

    def test_known_contact_is_not_automatically_hidden(self):
        self.db.upsert_crm_record(CRMRecord(id='contact-1',company='Known Co',contact='Seller',email='seller@example.com'))
        eq=self.service.process_input(self.payload)
        self.assertEqual(eq.status,'PENDING_APPROVAL')
        self.assertEqual(eq.recommendation.action,'REVIEW_JUNK')
        self.assertTrue(eq.match_candidates)

    def test_human_can_move_uncertain_junk_but_reject_does_not_hide_it(self):
        self.model.confidence='LOW'
        eq=self.service.process_input(self.payload)
        self.service.decide(eq.id,True,1)
        self.assertEqual(self.db.get_enquiry(eq.id).status,'JUNK')
        with self.assertRaises(ValueError):self.service.decide(eq.id,True,1)
        other=self.service.process_input({**self.payload,'id':'rejected-spam'})
        self.service.decide(other.id,False,1)
        self.assertEqual(self.db.get_enquiry(other.id).status,'REJECTED')

    def test_restore_preserves_history_and_prevents_automatic_requarantine(self):
        eq=self.service.process_input(self.payload)
        self.service.restore_junk(eq.id,1)
        restored=self.db.get_enquiry(eq.id)
        self.assertEqual(restored.status,'PENDING_APPROVAL')
        self.assertEqual(restored.recommendation.action,'REVIEW_RESTORED_ENQUIRY')
        self.assertEqual(restored.body,self.payload['body'])
        self.assertEqual(self.service.runs.current(eq.id),2)
        self.assertEqual(self.service.runs.snapshot(eq.id,1)['status'],'JUNK')
        self.assertEqual(len(self.model.calls),1)
        with self.assertRaises(ValueError):self.service.restore_junk(eq.id,1)
        rerun=self.service.rerun(eq.id,'full','after-restore-001')
        self.assertEqual(rerun.status,'PENDING_APPROVAL')
        self.assertEqual(rerun.recommendation.action,'REVIEW_JUNK')

    def test_not_junk_can_restore_uncertain_review_and_supersedes_old_action(self):
        self.model.confidence='LOW'
        eq=self.service.process_input(self.payload)
        self.service.restore_junk(eq.id,1)
        old=next(a for a in self.db.list_actions_for_enquiry(eq.id) if a.payload['run_version']==1)
        self.assertEqual(old.status,'SUPERSEDED')
        self.assertEqual(self.db.get_enquiry(eq.id).recommendation.action,'REVIEW_RESTORED_ENQUIRY')
        with self.assertRaises(ValueError):self.service.decide(eq.id,True,1)

    def test_draft_only_cannot_bypass_junk_policy(self):
        eq=self.service.process_input(self.payload)
        with self.assertRaises(ValueError):self.service.rerun(eq.id,'draft','draft-junk-001')
        self.assertEqual(self.service.runs.current(eq.id),1)

    def test_sales_and_unclear_inputs_are_not_forced_into_junk(self):
        for category in ('sales','unknown'):
            self.model.category=category
            eq=self.service.process_input({**self.payload,'id':category})
            self.assertEqual(eq.status,'PENDING_APPROVAL')
            self.assertNotEqual(eq.recommendation.action,'REVIEW_JUNK')
            self.assertIsNotNone(eq.draft_response)
