import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from beda.live import LiveService
from beda.storage import Database
from beda.llm import Analysis, Draft, ModelError
from beda.research import ResearchPlan, ResearchAnswer, Citation, research, retrieve
from beda.models import Enquiry


class ResearchModel:
    model='explicit-test-double'
    key='test'
    def __init__(self,missing=False,bad_quote=False):
        self.calls=[];self.missing=missing;self.bad_quote=bad_quote
    def generate(self,instruction,data,schema,log):
        self.calls.append((schema,data))
        if schema is Analysis:
            return Analysis(category='technical',confidence='HIGH',facts=[],missing_fields=['specification'] if self.missing else [],
                constraints=['Engineering sign-off required'],needs_research=True,rationale='Technical question')
        if schema is ResearchPlan:return ResearchPlan(queries=['harmonics THD engineer'])
        if schema is ResearchAnswer:
            source=data['sources'][0]
            return ResearchAnswer(evidence=[Citation(source_id=source['source_id'],quote='invented limit' if self.bad_quote else source['text'])],unresolved_questions=['Numeric limits are not established.'])
        if schema is Draft:return Draft(text='An engineer needs to review the applicable limits.')
        raise AssertionError(schema)


class ResearchRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.tmp.name)/'test.db'));self.db.initialize()
        self.model=ResearchModel();self.service=LiveService(self.db,self.model)
        self.payload={'id':'new-technical','body':'Please advise on harmonics THD limits.'}
    def tearDown(self):self.tmp.cleanup()
    def test_research_precedes_draft_and_supplies_validated_citations(self):
        self.service.process_input(self.payload)
        self.assertEqual([s for s,_ in self.model.calls],[Analysis,ResearchPlan,ResearchAnswer,Draft])
        draft_input=self.model.calls[-1][1]
        self.assertTrue(draft_input['research']['citations'])
        self.assertEqual(draft_input['research']['status'],'INSUFFICIENT_EVIDENCE')
        events=[e.event_type for e in self.db.list_audit('new-technical')]
        self.assertLess(events.index('RESEARCH_COMPLETED'),events.index('DRAFTED'))
        self.assertEqual(self.db.get_enquiry('new-technical').recommendation.action,'ESCALATE_TO_EXPERT')
    def test_missing_information_skips_research_for_clarification(self):
        self.model.missing=True;self.service.process_input(self.payload)
        self.assertEqual([s for s,_ in self.model.calls],[Analysis,Draft])
    def test_fabricated_citation_not_passed_to_drafting(self):
        self.model.bad_quote=True;self.service.process_input(self.payload)
        self.assertEqual(self.model.calls[-1][1]['research']['citations'],[])
        self.assertNotIn('rejected_citations',self.model.calls[-1][1]['research'])
        result=next(e for e in self.db.list_audit('new-technical') if e.event_type=='RESEARCH_COMPLETED')
        self.assertTrue(result.details['rejected_citations'])
    def test_rerun_preserves_snapshot_and_invalidates_old_approval(self):
        self.service.process_input(self.payload)
        old=self.db.list_actions_for_enquiry('new-technical')[0]
        self.service.rerun('new-technical','full','request-full-001')
        self.assertEqual(self.service.runs.current('new-technical'),2)
        self.assertEqual(self.service.runs.snapshot('new-technical',1)['status'],'PENDING_APPROVAL')
        self.assertEqual(self.db.get_action(old.id).status,'SUPERSEDED')
        with self.assertRaises(ValueError):self.service.decide('new-technical',True,1)
        self.service.decide('new-technical',True,2)
        self.assertEqual(self.service.runs.snapshot('new-technical',2)['status'],'COMPLETED')
        self.service.rerun('new-technical','full','request-full-001')
        self.assertEqual(self.service.runs.current('new-technical'),2)
    def test_draft_regeneration_reuses_research_but_requires_fresh_approval(self):
        self.service.process_input(self.payload);self.model.calls.clear()
        self.service.rerun('new-technical','draft','request-draft-001')
        self.assertEqual([s for s,_ in self.model.calls],[Draft])
        self.assertTrue(self.model.calls[-1][1]['research']['citations'])
        self.assertEqual(self.db.get_enquiry('new-technical').status,'PENDING_APPROVAL')
        self.assertEqual(len(self.db.list_actions_for_enquiry('new-technical')),2)
    def test_no_sources_and_research_failure_do_not_invent_answer(self):
        eq=Enquiry(id='a',source_message_id='a',body='THD limits')
        events=[]
        result=research(self.model,eq,lambda *e:events.append(e),Path(self.tmp.name)/'empty')
        self.assertEqual(result['status'],'INSUFFICIENT_EVIDENCE')
        with patch.object(self.model,'generate',side_effect=ModelError('Unavailable')):
            result=research(self.model,eq,lambda *e:events.append(e))
        self.assertEqual(result['status'],'FAILED')
        self.assertEqual(result['citations'],[])
    def test_retrieval_does_not_follow_symlink(self):
        corpus=Path(self.tmp.name)/'corpus';corpus.mkdir()
        secret=Path(self.tmp.name)/'outside.txt';secret.write_text('harmonics outside source')
        (corpus/'link.txt').symlink_to(secret)
        self.assertEqual(retrieve(['harmonics'],corpus=corpus),[])
