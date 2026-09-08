import tempfile
import unittest
from pathlib import Path
from tests.fixtures import fixtures

# This will fail to import if beda.service or beda.actions does not exist
from beda.service import EnquiryService
from beda.storage import Database


class TestService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")
        self.db = Database(self.db_path)
        self.db.initialize()
        # Seed CRM records into database
        for rec in fixtures.crm:
            self.db.upsert_crm_record(rec)
        self.service = EnquiryService(self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_e010_updates_e009_prospect_without_creating_second_record(self):
        self.service.process_input(fixtures.payload("E009"))
        correction = self.service.process_input(fixtures.payload("E010"))
        self.assertEqual(correction.related_enquiry_id, "E009")
        self.assertEqual(correction.recommendation.action, "UPDATE_CONTACT_PHONE")

    def test_consequential_action_needs_approval_and_is_idempotent(self):
        enquiry = self.service.process_input(fixtures.payload("E001"))
        actions = self.service.actions_for(enquiry.id)
        self.assertTrue(len(actions) > 0)
        self.assertEqual(actions[0].status, "PENDING_APPROVAL")

        first = self.service.approve_and_execute(enquiry.id, "reviewer")
        self.assertEqual(first.status, "SUCCEEDED")
        self.assertEqual(first.attempt_count, 1)

        # Execute again - should be idempotent and not increment attempt_count
        second = self.service.approve_and_execute(enquiry.id, "reviewer")
        self.assertEqual(first.idempotency_key, second.idempotency_key)
        self.assertEqual(second.attempt_count, 1)
        self.assertEqual(second.status, "SUCCEEDED")

    def test_staff_routing(self):
        e011 = self.service.process_input(fixtures.payload("E011"))
        self.assertEqual(e011.recommendation.owner, "Ali Pratama")

        e007 = self.service.process_input(fixtures.payload("E007"))
        self.assertEqual(e007.recommendation.owner, "Zidane Mouldino")

        e008 = self.service.process_input(fixtures.payload("E008"))
        self.assertEqual(e008.recommendation.owner, "Ties Rahardjo")

        e001 = self.service.process_input(fixtures.payload("E001"))
        self.assertEqual(e001.recommendation.owner, "Matt Cooper")

    def test_retry_pending_and_max_attempts(self):
        enquiry = self.service.process_input(fixtures.payload("E001"))
        action = self.service.actions_for(enquiry.id)[0]
        action.status = "FAILED_RETRYABLE"
        action.attempt_count = 1
        self.db.update_action(action)

        pending = self.service.executor.retry_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].status, "SUCCEEDED")
        self.assertEqual(pending[0].attempt_count, 2)


if __name__ == "__main__":
    unittest.main()
