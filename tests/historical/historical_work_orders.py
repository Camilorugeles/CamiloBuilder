import unittest

from tests.helpers.historical_governance import (
    commit_timestamp_rfc3339,
    require_ancestor,
    require_chronological_commits,
    require_commit,
)
from tests.test_lightweight_work_orders import FUNCTIONAL_COMMIT
from tests.test_work_order_registry import IMPLEMENTATION_COMMITS, WORK_ORDER_PATH, load_json


ROOT = WORK_ORDER_PATH.parents[2]


class HistoricalWorkOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work_009 = load_json(WORK_ORDER_PATH)

    def test_work_010_evidence_commit_exists_locally(self):
        require_commit(ROOT, FUNCTIONAL_COMMIT)

    def test_work_009_creation_matches_first_implementation_commit(self):
        first_commit_date = commit_timestamp_rfc3339(ROOT, IMPLEMENTATION_COMMITS[0])
        self.assertEqual(self.work_009["created_at"], first_commit_date)
        self.assertEqual(self.work_009["status_history"][0]["at"], first_commit_date)

    def test_work_009_commits_are_real_ancestral_remote_and_chronological(self):
        commits = self.work_009["implementation_commit_ids"]
        self.assertEqual(commits, IMPLEMENTATION_COMMITS)
        self.assertEqual(len(commits), len(set(commits)))
        for commit in commits:
            with self.subTest(commit=commit):
                self.assertEqual(len(commit), 40)
                require_commit(ROOT, commit)
                require_ancestor(ROOT, commit, "HEAD")
                require_ancestor(ROOT, commit, "origin/main")
        require_chronological_commits(ROOT, commits)

    def test_work_009_closure_commit_is_real_and_published(self):
        closure_commit = self.work_009["registry_closure_commit_id"]
        self.assertNotIn(closure_commit, self.work_009["implementation_commit_ids"])
        require_commit(ROOT, closure_commit)
        require_ancestor(ROOT, closure_commit, "origin/main")


if __name__ == "__main__":
    unittest.main()
