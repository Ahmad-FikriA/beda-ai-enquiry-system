import unittest
from tests.fixtures import fixtures

# This will fail to import if beda.matching does not exist
from beda.matching import find_candidates


class TestMatching(unittest.TestCase):
    def test_e002_returns_ambiguous_hume_candidates(self):
        candidates = find_candidates(
            fixtures.enquiry("E002"),
            fixtures.proposal("E002"),
            fixtures.crm,
            [],
        )
        candidate_ids = {c.crm_id for c in candidates}
        self.assertTrue({"C001", "C002"} <= candidate_ids)
        self.assertTrue(any(c.ambiguous for c in candidates))

    def test_e001_matches_c001_exact(self):
        candidates = find_candidates(
            fixtures.enquiry("E001"),
            fixtures.proposal("E001"),
            fixtures.crm,
            [],
        )
        self.assertTrue(len(candidates) > 0)
        self.assertEqual(candidates[0].crm_id, "C001")


if __name__ == "__main__":
    unittest.main()
