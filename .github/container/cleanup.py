"""Apply conservative GHCR retention using GitHub's API and the workflow token."""

import http.client
import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

GRACE_PERIOD = timedelta(days=7)
KEEP_SHA_VERSIONS = 30
SHA_TAG = re.compile(r"sha-[0-9a-f]{12}")
PR_TAG = re.compile(r"pr-(\d+)(?:-sha-[0-9a-f]{12})?")


def api(endpoint, method="GET", paginate=False):
    """Call GitHub's API, failing closed on permission or network errors."""
    if paginate:
        versions = []
        page = 1
        while True:
            batch = api(f"{endpoint}&page={page}")
            versions.extend(batch)
            if len(batch) < 100:
                return versions
            page += 1
    connection = http.client.HTTPSConnection("api.github.com", timeout=30)
    try:
        connection.request(
            method,
            endpoint,
            headers={
                "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "ai-playground-container-cleanup",
            },
        )
        response = connection.getresponse()
        body = response.read().decode()
        if not 200 <= response.status < 300:
            raise RuntimeError(f"GitHub API {method} {endpoint} failed ({response.status}): {body}")
        return json.loads(body) if body else None
    finally:
        connection.close()


def timestamp(value):
    """Parse an API timestamp as an aware UTC datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def tags_for(version):
    """Return every tag attached to a package version."""
    return version["metadata"]["container"]["tags"]


def recent_sha_ids(versions):
    """Keep the newest SHA-only versions across both publishing branches."""
    sha_versions = [
        version
        for version in versions
        if tags_for(version) and all(SHA_TAG.fullmatch(tag) for tag in tags_for(version))
    ]
    sha_versions.sort(key=lambda version: timestamp(version["created_at"]), reverse=True)
    return {version["id"] for version in sha_versions[:KEEP_SHA_VERSIONS]}


def deletion_reason(version, retained_ids, pull_request, now, protected_digests, delete_untagged=False):
    """Select only old, disposable versions without protected tags or digests."""
    if version["name"] in protected_digests:
        return None
    last_change = max(timestamp(version["created_at"]), timestamp(version["updated_at"]))
    if now - last_change < GRACE_PERIOD:
        return None
    tags = tags_for(version)
    if not tags:
        return "untagged for at least seven days" if delete_untagged else None
    if any(not SHA_TAG.fullmatch(tag) and not PR_TAG.fullmatch(tag) for tag in tags):
        return None
    pr_numbers = {int(match.group(1)) for tag in tags if (match := PR_TAG.fullmatch(tag))}
    if pr_numbers:
        for number in sorted(pr_numbers):
            details = pull_request(number)
            if details["state"] != "closed" or not details["closed_at"]:
                return None
            if now - timestamp(details["closed_at"]) < GRACE_PERIOD:
                return None
        return "all associated PRs closed for at least seven days"
    if version["id"] not in retained_ids:
        return "SHA-only version outside the newest 30"
    return None


def main():
    """List candidates and optionally delete them after checking their tags again."""
    repository = os.environ["GITHUB_REPOSITORY"]
    owner, package = repository.lower().split("/", 1)
    scope = "orgs" if os.environ["OWNER_TYPE"] == "Organization" else "users"
    endpoint = f"/{scope}/{quote(owner, safe='')}/packages/container/{quote(package, safe='')}/versions"
    dry_run = os.environ.get("DRY_RUN", "true").lower() != "false"
    delete_untagged = os.environ.get("DELETE_UNTAGGED", "false").lower() == "true"
    protected_digests = set(os.environ.get("PROTECTED_DIGESTS", "").replace(",", " ").split())
    versions = api(f"{endpoint}?per_page=100", paginate=True)
    retained_ids = recent_sha_ids(versions)
    now = datetime.now(timezone.utc)
    pull_requests = {}

    def pull_request(number):
        if number not in pull_requests:
            pull_requests[number] = api(f"/repos/{repository}/pulls/{number}")
        return pull_requests[number]

    candidates = []
    for version in versions:
        reason = deletion_reason(version, retained_ids, pull_request, now, protected_digests, delete_untagged)
        if reason:
            candidates.append((version, reason))
    print(f"Dry run: {dry_run}; {len(candidates)} candidates out of {len(versions)} versions.")
    for version, reason in candidates:
        print(
            f"{'Would delete' if dry_run else 'Candidate'} {version['id']} {version['name']} "
            f"{tags_for(version)}: {reason}"
        )
        if dry_run:
            continue
        fresh = api(f"{endpoint}/{version['id']}")
        if fresh != version:
            print(f"Skipping changed version {version['id']}.")
            continue
        pull_requests.clear()
        fresh_reason = deletion_reason(
            fresh, retained_ids, pull_request, datetime.now(timezone.utc), protected_digests, delete_untagged
        )
        if not fresh_reason:
            print(f"Skipping version {version['id']}: no longer eligible for deletion.")
            continue
        api(f"{endpoint}/{version['id']}", method="DELETE")
        print(f"Deleted {version['id']}.")


if __name__ == "__main__":
    main()
