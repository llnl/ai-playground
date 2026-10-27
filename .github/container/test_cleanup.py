"""Regression tests for safe package-version retention without network access."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from cleanup import deletion_reason, main, recent_sha_ids

NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)


def version(tags, identifier=1, age=10):
    """Create a minimal GitHub container-version response."""
    created = (NOW - timedelta(days=age)).isoformat()
    return {
        "id": identifier,
        "name": f"sha256:{identifier}",
        "created_at": created,
        "updated_at": created,
        "metadata": {"container": {"tags": tags}},
    }


class RetentionTests(unittest.TestCase):
    """Protect releases, active PRs, recent versions, and deployment digests."""

    def setUp(self):
        """Provide a PR that closed outside the grace period."""
        self.pull_request = Mock(return_value={"state": "closed", "closed_at": (NOW - timedelta(days=10)).isoformat()})

    def reason(self, image, retained=(), protected=(), delete_untagged=False):
        """Evaluate a version against fixed test inputs."""
        return deletion_reason(image, set(retained), self.pull_request, NOW, set(protected), delete_untagged)

    def test_release_and_unknown_tags_are_preserved(self):
        """Keep the entire digest if any tag is not recognized as disposable."""
        for tag in ["v1.2.3", "1.2", "latest", "develop", "main", "custom", "v2.0.0-rc1"]:
            with self.subTest(tag=tag):
                self.assertIsNone(self.reason(version(["sha-123456789abc", tag])))

    def test_recent_and_retained_sha_versions_are_preserved(self):
        """Keep young versions and the retained SHA history."""
        self.assertIsNone(self.reason(version(["sha-123456789abc"], age=1)))
        self.assertIsNone(self.reason(version(["sha-123456789abc"]), retained=[1]))
        self.assertIsNotNone(self.reason(version(["sha-123456789abc"])))

    def test_updated_versions_are_preserved(self):
        """Apply the grace period to updates as well as creation."""
        image = version(["sha-123456789abc"])
        image["updated_at"] = NOW.isoformat()
        self.assertIsNone(self.reason(image))

    def test_protected_digest_is_preserved(self):
        """Never delete an explicitly protected deployment digest."""
        self.assertIsNone(self.reason(version(["sha-123456789abc"]), protected=["sha256:1"]))

    def test_untagged_deletion_requires_opt_in_and_grace(self):
        """Untagged images might still be deployed by digest."""
        self.assertIsNone(self.reason(version([])))
        self.assertIsNotNone(self.reason(version([]), delete_untagged=True))
        self.assertIsNone(self.reason(version([], age=1), delete_untagged=True))

    def test_closed_pr_versions_are_candidates(self):
        """Both moving and SHA-specific PR tags belong to the same closed PR."""
        self.assertIsNotNone(self.reason(version(["pr-42", "pr-42-sha-123456789abc"])))
        self.pull_request.assert_called_once_with(42)

    def test_open_or_recently_closed_pr_is_preserved(self):
        """Wait until every associated PR has been closed for seven days."""
        for details in [
            {"state": "open", "closed_at": None},
            {"state": "closed", "closed_at": NOW.isoformat()},
        ]:
            self.pull_request.return_value = details
            self.assertIsNone(self.reason(version(["pr-42-sha-123456789abc"])))

    def test_multiple_pr_tags_are_all_checked(self):
        """Preserve shared digests while any associated PR remains open."""
        self.pull_request.side_effect = [self.pull_request.return_value, {"state": "open", "closed_at": None}]
        self.assertIsNone(self.reason(version(["pr-42", "pr-43"])))
        self.assertEqual(self.pull_request.call_count, 2)

    def test_newest_thirty_sha_only_versions_are_retained(self):
        """Do not count release or PR images toward branch history."""
        images = [version(["sha-123456789abc"], identifier=index, age=index) for index in range(40)]
        images.extend([version(["v1.0.0"], identifier=100), version(["pr-42"], identifier=101)])
        self.assertEqual(recent_sha_ids(images), set(range(30)))


class WorkflowTests(unittest.TestCase):
    """Verify dry-run and changed-version guards around actual API deletion."""

    def execute(self, dry_run, changed=False):
        """Run the entry point with mocked APIs and an old untagged image."""
        image = version([])
        image.update(created_at="2020-01-01T00:00:00Z", updated_at="2020-01-01T00:00:00Z")
        fresh = {**image, "metadata": {"container": {"tags": ["latest"]}}} if changed else image
        responses = [[image]] if dry_run else [[image], fresh, None]
        environment = {
            "GITHUB_REPOSITORY": "example/ai-playground",
            "OWNER_TYPE": "User",
            "DRY_RUN": str(dry_run).lower(),
            "DELETE_UNTAGGED": "true",
            "PROTECTED_DIGESTS": "",
        }
        with (
            patch.dict("os.environ", environment),
            patch("cleanup.api", side_effect=responses) as api_mock,
            patch("builtins.print"),
        ):
            main()
        return api_mock

    def test_dry_run_never_deletes(self):
        """A dry-run lists versions without calling DELETE."""
        api_mock = self.execute(dry_run=True)
        self.assertEqual(api_mock.call_count, 1)

    def test_changed_versions_are_not_deleted(self):
        """A newly added release tag protects a previously eligible version."""
        api_mock = self.execute(dry_run=False, changed=True)
        self.assertEqual(api_mock.call_count, 2)

    def test_unchanged_candidate_is_deleted(self):
        """Delete only after retrieving the unchanged version again."""
        api_mock = self.execute(dry_run=False)
        api_mock.assert_called_with("/users/example/packages/container/ai-playground/versions/1", method="DELETE")

    def execute_pr(self, fresh_details):
        """Refresh an unchanged PR image after its initially eligible PR state changes."""
        image = version(["pr-42"])
        image.update(created_at="2020-01-01T00:00:00Z", updated_at="2020-01-01T00:00:00Z")
        closed = {"state": "closed", "closed_at": "2020-01-01T00:00:00Z"}
        environment = {
            "GITHUB_REPOSITORY": "example/ai-playground",
            "OWNER_TYPE": "User",
            "DRY_RUN": "false",
        }
        responses = [[image], closed, image, fresh_details, None]
        with (
            patch.dict("os.environ", environment, clear=True),
            patch("cleanup.api", side_effect=responses) as api_mock,
            patch("builtins.print"),
        ):
            main()
        self.assertEqual(
            sum(call.args[0] == "/repos/example/ai-playground/pulls/42" for call in api_mock.call_args_list), 2
        )
        return api_mock

    def test_reopened_pr_is_not_deleted(self):
        """Protect an image when its PR reopens after candidate selection."""
        api_mock = self.execute_pr({"state": "open", "closed_at": None})
        self.assertFalse(any(call.kwargs.get("method") == "DELETE" for call in api_mock.call_args_list))

    def test_recently_reclosed_pr_is_not_deleted(self):
        """Restart the grace period if a PR closes again after candidate selection."""
        api_mock = self.execute_pr({"state": "closed", "closed_at": datetime.now(timezone.utc).isoformat()})
        self.assertFalse(any(call.kwargs.get("method") == "DELETE" for call in api_mock.call_args_list))

    def test_still_eligible_pr_is_deleted_after_refresh(self):
        """Keep deleting eligible images after a second independent PR-state check."""
        api_mock = self.execute_pr({"state": "closed", "closed_at": "2020-01-01T00:00:00Z"})
        api_mock.assert_called_with("/users/example/packages/container/ai-playground/versions/1", method="DELETE")


if __name__ == "__main__":
    unittest.main()
