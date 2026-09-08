import unittest
from tests.fixtures import fixtures

# This will fail to import if beda.reasoning does not exist
from beda.reasoning import propose


class TestReasoning(unittest.TestCase):
    def test_e005_keeps_missing_bill_and_fixture_schedule(self):
        proposal = propose(fixtures.enquiry("E005"), fixtures.attachment("E005"))
        self.assertTrue({"electricity_bill", "fixture_schedule"} <= set(proposal.missing_fields))

    def test_e004_junk_has_no_draft_and_archives(self):
        proposal = propose(fixtures.enquiry("E004"), None)
        self.assertEqual(proposal.category, "junk")
        self.assertEqual(proposal.recommended_action, "ARCHIVE_JUNK")

    def test_e006_escalation_no_engineered_thd_answer(self):
        proposal = propose(fixtures.enquiry("E006"), None)
        self.assertEqual(proposal.category, "technical/escalation")
        self.assertEqual(proposal.recommended_action, "ESCALATE_TECHNICAL")

    def test_e008_never_confirms_progress(self):
        proposal = propose(fixtures.enquiry("E008"), None)
        self.assertIn("NEVER_CONFIRM_PROGRESS", proposal.constraints)

    def test_e012_retains_landlord_approval_constraint(self):
        proposal = propose(fixtures.enquiry("E012"), None)
        self.assertTrue(any("landlord" in c.lower() for c in proposal.constraints))


if __name__ == "__main__":
    unittest.main()
