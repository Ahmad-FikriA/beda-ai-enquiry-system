import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from beda.llm import Analysis, Fact, Draft, ModelError, Gemini
from beda.live import LiveService
from beda.storage import Database
from urllib.error import HTTPError


class FakeModel:
    model = 'test-double'
    key = 'test'
    def generate(self, instruction, data, schema, log):
        if schema is Draft:
            return Draft(text='Thank you. Could you supply a recent bill?')
        return Analysis(category='sales', confidence='HIGH', facts=[Fact(name='phone',value='0400 123 456',evidence='Call 0400 123 456'),
            Fact(name='company',value='Invented Ltd',evidence='Not in source')],missing_fields=['bill'],constraints=[],needs_research=False,rationale='Sales enquiry')


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Database(str(Path(self.tmp.name)/'test.db'));self.db.initialize()
        self.service=LiveService(self.db,FakeModel())
    def tearDown(self):
        self.tmp.cleanup()
    def test_unsupported_facts_removed_and_duplicate_no_new_action(self):
        payload={'id':'novel','body':'Call 0400 123 456 for solar'}
        eq=self.service.process_input(payload)
        self.assertNotIn('company',eq.proposal.extracted_fields)
        self.assertEqual(eq.proposal.confidence,'LOW')
        self.assertEqual(eq.status,'PENDING_APPROVAL')
        self.service.process_input(payload)
        self.assertEqual(len(self.db.list_actions_for_enquiry('novel')),1)
    def test_approval_records_only_local_effect_and_reject_is_terminal(self):
        self.service.process_input({'id':'a','body':'Call 0400 123 456'})
        self.service.decide('a',False)
        with self.assertRaises(ValueError):self.service.decide('a',True)
        self.assertEqual(self.db.list_actions_for_enquiry('a')[0].status,'REJECTED')
    def test_model_failure_persisted_and_can_retry(self):
        with patch.object(self.service.model,'generate',side_effect=ModelError('Quota')):
            eq=self.service.process_input({'id':'b','body':'solar'})
        self.assertEqual(eq.status,'MODEL_FAILED')
        self.assertEqual(self.db.list_actions_for_enquiry('b'),[])
        eq=self.service.process_input({'id':'b','body':'solar'})
        self.assertEqual(eq.status,'PENDING_APPROVAL')
    def test_missing_key_never_falls_back(self):
        with patch.dict('os.environ',{'GEMINI_API_KEY':''}):
            with self.assertRaises(ModelError):Gemini().generate('',{},Analysis,lambda *args:None)
    def test_prompt_preview_includes_exact_input_without_transport_secret(self):
        events=[]
        with patch.dict('os.environ',{'GEMINI_API_KEY':'transport-secret-value'}), patch('beda.llm.urlopen',side_effect=HTTPError('https://example.test',401,'failure',{},None)):
            with self.assertRaises(ModelError):
                Gemini().generate('Classify safely',{'body':'Synthetic message'},Analysis,lambda *e:events.append(e))
        preview=next(details for event,details in events if event=='PROMPT_PREVIEW')
        self.assertEqual(preview['input'],{'body':'Synthetic message'})
        self.assertIn('Classify safely',preview['system_instruction'])
        self.assertEqual(preview['stage'],'extract')
        self.assertNotIn('transport-secret-value',str(events))
    def test_auth_error_not_retried_and_rate_limit_bounded(self):
        with patch.dict('os.environ',{'GEMINI_API_KEY':'unit-test-placeholder'}):
            for code, attempts in [(401,1),(429,3)]:
                events=[]
                with patch('beda.llm.urlopen',side_effect=HTTPError('https://example.test',code,'failure',{},None)) as transport, patch('beda.llm.time.sleep'):
                    with self.assertRaises(ModelError):
                        Gemini().generate('',{},Analysis,lambda *event:events.append(event))
                    self.assertEqual(transport.call_count,attempts)
                    self.assertEqual(sum(e[0]=='LLM_FAILURE' for e in events),attempts)
    def test_fixture_import_keeps_unquoted_subject_comma_with_warning(self):
        from beda.workspace import fixtures
        row=next(r for r in fixtures() if r['id']=='E004')
        self.assertEqual(row['subject'],'Buy 50,000 Australian CEO leads today')
        self.assertIn('cryptocurrency',row['body'])
        self.assertIn('import_warning',row)

if __name__=='__main__':unittest.main()
