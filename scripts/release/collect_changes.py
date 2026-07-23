"""
Collect raw change lines from GitHub for AI changelog generation.

Sources:
1. PR titles via GitHub's auto-generated release notes API
2. Commit messages via commit comparison API

Extracted from gemma-plugin.yml lines 162–221.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field

from scripts.utils.github import (
    find_previous_tag,
    generate_release_notes,
    compare_commits,
)

logger = logging.getLogger(__name__)


@dataclass
class CollectedChanges:
    """Container for raw change lines collected from GitHub."""

    raw_lines: list[str] = field(default_factory=list)
    pr_count: int = 0
    commit_count: int = 0
    previous_tag: str | None = None


def _clean_line(line: str) -> str:
    """Clean a single change line by removing noise.

    Strips:
    - Leading bullet markers (* )
    - Author attributions (by @user in https://...)
    - Trailing URLs
    - Trailing ellipsis
    - Conventional commit prefixes (feat:, fix:, etc.)
    """
    cleaned = line.strip()
    cleaned = re.sub(r"^\*\s+", "", cleaned)
    cleaned = re.sub(r"\s+by @[\w-]+ in https?://\S+", "", cleaned)
    cleaned = re.sub(r"\s+in https?://\S+", "", cleaned)
    cleaned = re.sub(r"…$", "", cleaned)
    cleaned = re.sub(
        r"^(feat|fix|refactor|perf|docs|style|test|chore|build)(\([^)]*\))?[!:]?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


def _is_noise(line: str) -> bool:
    """Check if a change line is noise that should be filtered out."""
    if not line or len(line) < 5:
        return True
    checks = [
        (r"^Merge (branch|pull request)", re.IGNORECASE),
        (r"^(Bugfix|Feature|Hotfix)/", re.IGNORECASE),
        (r"^release v\d+", re.IGNORECASE),
        (r"^update changelog", re.IGNORECASE),
        (r"^(chore|ci|bump|wip)\s*[:(]", re.IGNORECASE),
        (r"^merge\s", re.IGNORECASE),
    ]
    for pattern, flags in checks:
        if re.search(pattern, line, flags):
            return True
    return False


def _deduplicate(lines: list[str]) -> list[str]:
    """Deduplicate lines case-insensitively, preserving first occurrence's casing."""
    seen: dict[str, str] = {}
    for line in lines:
        key = line.lower()
        if key not in seen:
            seen[key] = line
    return list(seen.values())


def collect_changes(
    owner: str,
    repo: str,
    tag: str,
    token: str,
    max_lines: int = 25,
) -> CollectedChanges:
    """Collect raw change lines from GitHub for a release.

    Combines PR titles (from auto-generated release notes) and commit messages
    (from commit comparison), cleans and deduplicates them.

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.
        tag: The tag being released (e.g. "v1.5.0").
        token: GitHub API token.
        max_lines: Maximum number of lines to return.

    Returns:
        CollectedChanges with deduplicated, cleaned change lines.
    """
    result = CollectedChanges()

    # Find previous tag
    result.previous_tag = find_previous_tag(owner, repo, token, tag)
    logger.info("Previous tag: %s", result.previous_tag or "(none — first release)")

    pr_lines: list[str] = []
    commit_lines: list[str] = []

    # Source A: PR titles from auto-generated release notes
    try:
        notes_body = generate_release_notes(owner, repo, tag, result.previous_tag, token)
        pr_lines = [
            _clean_line(line)
            for line in notes_body.split("\n")
            if line.startswith("* ")
        ]
        pr_lines = [line for line in pr_lines if not _is_noise(line)]
        result.pr_count = len(pr_lines)
        logger.info("PR lines collected: %d", result.pr_count)
    except Exception as e:
        logger.warning("generateReleaseNotes failed: %s", e)

    # Source B: Direct commit messages
    if result.previous_tag:
        try:
            commits = compare_commits(owner, repo, result.previous_tag, "HEAD", token)
            commit_lines = [
                _clean_line(c["commit"]["message"].split("\n")[0])
                for c in commits
            ]
            commit_lines = [line for line in commit_lines if not _is_noise(line)]
            result.commit_count = len(commit_lines)
            logger.info("Commit lines collected: %d", result.commit_count)
        except Exception as e:
            logger.warning("compareCommits failed: %s", e)

    # Merge, deduplicate, and cap
    all_lines = _deduplicate([*pr_lines, *commit_lines])
    result.raw_lines = all_lines[:max_lines]
    logger.info("Total raw lines for AI: %d", len(result.raw_lines))

    return result
