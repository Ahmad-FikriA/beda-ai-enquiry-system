import tempfile
import unittest
from pathlib import Path
from beda.documents import Documents, SOURCE
from beda.storage import Database
from beda.live import LiveService
from tests.test_live import FakeModel


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Database(str(Path(self.tmp.name)/'test.db'));self.db.initialize()
        self.service=LiveService(self.db,FakeModel());self.docs=self.service.documents
        self.filename='01_hume_energy_bill.txt'
    def tearDown(self):self.tmp.cleanup()
    def test_three_readable_originals_and_revision_save_preserves_files(self):
        original=(SOURCE/self.filename).read_bytes()
        self.assertEqual(len(self.docs.list()),3)
        before=self.docs.get(self.filename)['current']['content']
        self.docs.save(self.filename,before+'\nReviewer note: verify meter reading.','Added a review note',1)
        document=self.docs.get(self.filename)
        self.assertEqual(document['current']['revision'],2)
        self.assertEqual(document['revisions'][1]['content'],before)
        self.assertEqual((SOURCE/self.filename).read_bytes(),original)
        with self.assertRaises(ValueError):self.docs.save(self.filename,'Stale edit','Old tab',1)
    def test_full_rerun_uses_latest_copy_but_preserves_old_input_snapshot(self):
        payload=self.docs.attach({'id':'E001','body':'Call 0400 123 456','attachment_filename':self.filename})
        old=self.service.process_input(payload)
        original=old.attachment_content
        self.docs.save(self.filename,original+'\nWorking-copy correction.','Demo correction',1)
        latest=self.service.rerun('E001','full','document-rerun-001')
        self.assertIn('Working-copy correction.',latest.attachment_content)
        self.assertEqual(latest.raw_payload['attachment_revision'],2)
        self.assertEqual(self.service.runs.snapshot('E001',1)['attachment_content'],original)
        events=[a for a in self.db.list_audit('E001') if a.event_type=='ATTACHMENT_SELECTED']
        self.assertEqual([a.details['revision'] for a in events],[1,2])
    def test_draft_only_does_not_silently_refresh_document(self):
        payload=self.docs.attach({'id':'E001','body':'Call 0400 123 456','attachment_filename':self.filename})
        self.service.process_input(payload)
        self.docs.save(self.filename,'A changed source document.','Replace working copy',1)
        regenerated=self.service.rerun('E001','draft','document-draft-001')
        self.assertEqual(regenerated.attachment_content,payload['attachment_content'])
        self.assertEqual(regenerated.raw_payload['attachment_revision'],1)
    def test_unknown_document_and_blank_content_rejected(self):
        with self.assertRaises(ValueError):self.docs.save('../outside.txt','text','note',1)
        with self.assertRaises(ValueError):self.docs.save(self.filename,'','note',1)
