"""
GitHub REST API helpers for the GEMMA release pipeline.

Provides thin wrappers around the GitHub REST API for:
- Listing tags
- Comparing commits
- Generating release notes
- Getting contributors from git log
"""

from __future__ import annotations

import logging
import re
import subprocess
from typing import Any

import requests

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _headers(token: str) -> dict[str, str]:
    """Build standard headers for GitHub API requests."""
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _api_get(endpoint: str, token: str, params: dict | None = None) -> Any:
    """Make a GET request to the GitHub API."""
    url = f"{GITHUB_API}{endpoint}"
    resp = requests.get(url, headers=_headers(token), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _api_post(endpoint: str, token: str, json_data: dict) -> Any:
    """Make a POST request to the GitHub API."""
    url = f"{GITHUB_API}{endpoint}"
    resp = requests.post(url, headers=_headers(token), json=json_data, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ── Tag operations ────────────────────────────────────────────────────────────


def get_latest_tags(
    owner: str,
    repo: str,
    token: str,
    count: int = 20,
) -> list[str]:
    """List the most recent tags from the repository.

    Returns:
        List of tag name strings, e.g. ["v1.5.0", "v1.4.2", ...].
    """
    data = _api_get(f"/repos/{owner}/{repo}/tags", token, params={"per_page": count})
    return [tag["name"] for tag in data]


def find_previous_tag(
    owner: str,
    repo: str,
    token: str,
    current_tag: str,
    count: int = 20,
) -> str | None:
    """Find the previous stable release tag (e.g. vX.Y.Z) before the current tag.

    Filters tags to only include stable semver tags (no pre-release suffixes),
    excludes the current tag, and returns the highest remaining version.

    Returns:
        Previous tag name or None if this is the first release.
    """
    tags = get_latest_tags(owner, repo, token, count)
    stable_tags = [
        t for t in tags
        if re.match(r"^v\d+\.\d+\.\d+$", t) and t != current_tag
    ]

    if not stable_tags:
        return None

    # Sort descending by numeric version
    stable_tags.sort(
        key=lambda t: tuple(int(x) for x in t.lstrip("v").split(".")),
        reverse=True,
    )
    return stable_tags[0]


# ── Commit comparison ─────────────────────────────────────────────────────────


def compare_commits(
    owner: str,
    repo: str,
    base: str,
    head: str,
    token: str,
) -> list[dict[str, Any]]:
    """Compare two refs and return the list of commits between them.

    Returns:
        List of commit objects from the GitHub API.
    """
    data = _api_get(
        f"/repos/{owner}/{repo}/compare/{base}...{head}",
        token,
    )
    return data.get("commits", [])


# ── Release notes generation ─────────────────────────────────────────────────


def generate_release_notes(
    owner: str,
    repo: str,
    tag: str,
    previous_tag: str | None,
    token: str,
) -> str:
    """Generate release notes via GitHub's auto-generated release notes API.

    Returns:
        The raw markdown body of the generated release notes.
    """
    payload: dict[str, str] = {
        "tag_name": tag,
    }
    if previous_tag:
        payload["previous_tag_name"] = previous_tag

    data = _api_post(
        f"/repos/{owner}/{repo}/releases/generate-notes",
        token,
        payload,
    )
    return data.get("body", "")


# ── Contributors ──────────────────────────────────────────────────────────────


def get_contributors(count: int = 30) -> list[str]:
    """Get unique contributor names from git log.

    Filters out bots and github-actions. Falls back to a default list
    if git is unavailable.

    Returns:
        List of unique contributor names.
    """
    try:
        result = subprocess.run(
            ["git", "log", f"--format=%aN", f"-{count}"],
            capture_output=True,
            text=True,
            check=True,
        )
        names = result.stdout.strip().split("\n")
        # Filter bots and deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for name in names:
            name = name.strip()
            if not name:
                continue
            if "[bot]" in name or "github-actions" in name:
                continue
            if name not in seen:
                seen.add(name)
                unique.append(name)
        return unique[:10]
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("Could not get contributors from git log — using defaults")
        return ["kentemman-gmd", "velascojasper0"]


# ── Tag existence check ───────────────────────────────────────────────────────


def tag_exists(tag: str) -> bool:
    """Check if a git tag exists locally.

    Returns:
        True if the tag exists in the local repository.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", f"refs/tags/{tag}"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        logger.warning("git not found — assuming tag does not exist")
        return False
