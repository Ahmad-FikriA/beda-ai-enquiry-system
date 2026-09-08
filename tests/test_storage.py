import tempfile
import unittest
from pathlib import Path

# When models and storage do not exist yet, this will fail to import
from beda.models import Enquiry
from beda.storage import Database


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_database_persists_enquiry_and_audit(self):
        db = Database(self.db_path)
        db.initialize()
        db.create_enquiry(Enquiry(id="E001", source_message_id="E001", subject="Solar"))
        db.add_audit("E001", "RECEIVED", "system", {"source": "fixture"})

        enquiry = db.get_enquiry("E001")
        self.assertIsNotNone(enquiry)
        self.assertEqual(enquiry.subject, "Solar")

        audits = db.list_audit("E001")
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].event_type, "RECEIVED")

    def test_find_by_source_id(self):
        db = Database(self.db_path)
        db.initialize()
        db.create_enquiry(Enquiry(id="E001", source_message_id="SRC-123", subject="Solar"))
        found = db.find_by_source_id("SRC-123")
        self.assertIsNotNone(found)
        self.assertEqual(found.id, "E001")

        not_found = db.find_by_source_id("DOES-NOT-EXIST")
        self.assertIsNone(not_found)


if __name__ == "__main__":
    unittest.main()
