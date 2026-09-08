import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

# This will fail to import if beda.importer does not exist
from beda.importer import cleanup_raw_content, import_fixture_pack
from beda.models import Enquiry
from beda.service import EnquiryService
from beda.storage import Database

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class TestImporter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")
        self.db = Database(self.db_path)
        self.db.initialize()
        self.service = EnquiryService(self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_import_processes_all_twelve_fixture_enquiries(self):
        ids = import_fixture_pack(self.service, DATA_DIR)
        expected = [f"E{i:03}" for i in range(1, 13)]
        self.assertEqual(ids, expected)

        # Check all 12 are in db
        enquiries = self.db.list_enquiries()
        self.assertEqual(len(enquiries), 12)

        # Check CRM records were seeded
        crm = self.db.list_crm_records()
        self.assertTrue(len(crm) >= 5)

    def test_cleanup_raw_content_redacts_older_records(self):
        # Create an enquiry with an old timestamp
        old_time = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
        enquiry = Enquiry(
            id="E999",
            source_message_id="E999",
            sender="old@example.com",
            subject="Old Enquiry",
            body="Sensitive body details",
            attachment_content="Sensitive invoice data",
            received_at=old_time,
            raw_payload={"id": "E999", "body": "Sensitive body details", "attachment_content": "Sensitive invoice data"},
        )
        self.db.create_enquiry(enquiry)
        self.db.add_audit("E999", "RECEIVED", "system", {"source": "archive"})

        # Clean up records older than 30 days
        redacted_count = cleanup_raw_content(self.db, older_than_days=30)
        self.assertEqual(redacted_count, 1)

        # Verify raw body and attachment are redacted
        cleaned = self.db.get_enquiry("E999")
        self.assertIn("REDACTED", cleaned.body)
        self.assertIsNone(cleaned.attachment_content)

        # Verify audit record remains
        audits = self.db.list_audit("E999")
        self.assertEqual(len(audits), 1)


if __name__ == "__main__":
    unittest.main()
