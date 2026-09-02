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


def _clean_line(line: str, author_login: str | None = None, owner: str = "", repo: str = "") -> str:
    """Clean a single change line by removing noise, stripping embedded tags, and attaching canonical author mention link and PR/issue links.

    Strips:
    - Leading bullet markers (*, -)
    - Embedded author & PR tags (e.g. (@user #123), (@user), (#123), ([@user](url)), ([#123](url)))
    - Author attributions (by @user in https://...)
    - Trailing URLs
    - Trailing ellipsis
    - Conventional commit prefixes (feat:, fix:, etc.)
    """
    cleaned = line.strip()

    # 1. Extract PR number and URL
    pr_num = None
    pr_url = None
    # 1a. Explicit PR / issue URL
    url_match = re.search(r"https?://github\.com/([^/]+)/([^/]+)/(?:pull|issues)/(\d+)", cleaned)
    if url_match:
        pr_num = url_match.group(3)
        pr_url = url_match.group(0)
    else:
        # 1b. Markdown PR link: [#123](url)
        md_pr_match = re.search(r"\[\s*#(\d+)\s*\]\((https?://[^\s)]+)\)", cleaned)
        if md_pr_match:
            pr_num = md_pr_match.group(1)
            pr_url = md_pr_match.group(2)
        else:
            # 1c. Compound parenthesized tag: (@user #123) or (@user, #123)
            compound_match = re.search(r"\(@[\w-]+\s*(?:[,&/-]\s*|\s+)#?(\d+)\)", cleaned)
            if compound_match:
                pr_num = compound_match.group(1)
            else:
                # 1d. Plain (#123) or trailing #123
                num_match = re.search(r"\(\s*#(\d+)\s*\)", cleaned)
                if num_match:
                    pr_num = num_match.group(1)
                else:
                    trailing_num = re.search(r"(?:^|\s)#(\d+)(?:\s*$)", cleaned)
                    if trailing_num:
                        pr_num = trailing_num.group(1)

    if pr_num and not pr_url and owner and repo:
        pr_url = f"https://github.com/{owner}/{repo}/pull/{pr_num}"

    # 2. Extract author username (prioritize embedded user tag over commit author)
    author = None
    # 2a. Embedded in (@user #123) or (@user) or ([@user](...))
    embedded_author_match = re.search(
        r"\(\s*\[?@([\w-]+)\]?(?:\([^)]*\))?(?:\s*[,&/-]?\s*#?\d+)?\s*\)", cleaned
    )
    if embedded_author_match:
        author = embedded_author_match.group(1)
    else:
        # 2b. Markdown link [@user](...)
        md_author_match = re.search(r"\[\s*@([\w-]+)\s*\](?:\([^)]*\))?", cleaned)
        if md_author_match:
            author = md_author_match.group(1)
        else:
            # 2c. "by @user" in release notes
            by_author_match = re.search(r"\sby\s+@([\w-]+)", cleaned)
            if by_author_match:
                author = by_author_match.group(1)
            elif author_login:
                author = author_login

    if author and ("[bot]" in author.lower() or "github-actions" in author.lower()):
        author = None

    # 3. Strip noise, prefixes, and all embedded author / PR tags from the text
    # Strip leading bullet points
    cleaned = re.sub(r"^[\s*\-•]+\s*", "", cleaned)
    # Strip "by @user in https://..." or "in https://..." (safe against eating parens)
    cleaned = re.sub(r"\s+by\s+@[\w-]+(?:\s+in\s+https?://[^\s)]+)?", "", cleaned)
    cleaned = re.sub(r"\s+in\s+https?://[^\s)]+", "", cleaned)
    # Strip outer parens enclosing markdown links: ([@user](url)) or ([#123](url))
    cleaned = re.sub(r"\(\s*\[\s*@[\w-]+\s*\]\([^)]+\)\s*\)", "", cleaned)
    cleaned = re.sub(r"\(\s*\[\s*#\d+\s*\]\([^)]+\)\s*\)", "", cleaned)
    # Strip compound author/PR parenthesized tags: (@user #123), (@user, #123), ([@user](url) [#123](url))
    cleaned = re.sub(
        r"\(\s*\[?@[\w-]+\]?(?:\([^)]*\))?\s*(?:[,&/\-]\s*|\s+)?\[?#\d+\]?(?:\([^)]*\))?\s*\)",
        "",
        cleaned,
    )
    cleaned = re.sub(
        r"\(\s*\[?#\d+\]?(?:\([^)]*\))?\s*(?:[,&/\-]\s*|\s+)?\[?@[\w-]+\]?(?:\([^)]*\))?\s*\)",
        "",
        cleaned,
    )
    # Strip single parenthesized tags: (@user), (#123)
    cleaned = re.sub(r"\(\s*\[?@[\w-]+\]?(?:\([^)]*\))?\s*\)", "", cleaned)
    cleaned = re.sub(r"\(\s*\[?#\d+\]?(?:\([^)]*\))?\s*\)", "", cleaned)
    # Strip bare markdown links or brackets: [@user](url), [#123](url)
    cleaned = re.sub(r"\[\s*@[\w-]+\s*\]\([^)]+\)", "", cleaned)
    cleaned = re.sub(r"\[\s*#\d+\s*\]\([^)]+\)", "", cleaned)
    cleaned = re.sub(r"\[\s*@[\w-]+\s*\]", "", cleaned)
    cleaned = re.sub(r"\[\s*#\d+\s*\]", "", cleaned)
    # Strip remaining bare URLs without consuming closing parens
    cleaned = re.sub(r"https?://[^\s)]+", "", cleaned)
    # Strip standalone @user or #123 tokens
    cleaned = re.sub(r"(?:^|\s)@[\w-]+(?:\s|$)", " ", cleaned)
    cleaned = re.sub(r"(?:^|\s)#\d+(?:\s|$)", " ", cleaned)
    # Strip conventional commit prefixes (e.g. feat:, fix(scope):, feat!:)
    cleaned = re.sub(
        r"^(feat|fix|refactor|perf|docs|style|test|chore|build|ci)(\([^)]*\))?[!:]\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Strip trailing ellipsis and punctuation
    cleaned = re.sub(r"[…\.]+$", "", cleaned)
    cleaned = re.sub(r"[\s,;:\-()]+$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # 4. Attach single canonical linked author and PR tags
    suffix_parts: list[str] = []
    if author:
        suffix_parts.append(f"([@{author}](https://github.com/{author}))")
    if pr_num:
        if pr_url:
            suffix_parts.append(f"([#{pr_num}]({pr_url}))")
        else:
            suffix_parts.append(f"(#{pr_num})")

    if suffix_parts:
        return f"{cleaned} {' '.join(suffix_parts)}"
    return cleaned


def _is_noise(line: str) -> bool:
    """Check if a change line is noise that should be filtered out."""
    if not line or len(line.strip()) < 5:
        return True
    checks = [
        (r"^Merge (branch|pull request)", re.IGNORECASE),
        (r"^(Bugfix|Feature|Hotfix)/", re.IGNORECASE),
        (r"^release\s+(v?\d+|stable|preview)", re.IGNORECASE),
        (r"^update changelog", re.IGNORECASE),
        (r"^update metadata and release data", re.IGNORECASE),
        (r"^update release-(stable|preview)", re.IGNORECASE),
        (r"^(chore|ci|bump|wip|build)\s*[:(]", re.IGNORECASE),
        (r"^merge\s", re.IGNORECASE),
        (r"beta channel", re.IGNORECASE),
        (r"github-actions", re.IGNORECASE),
        (r"\[bot\]", re.IGNORECASE),
        (r"\[skip ci\]", re.IGNORECASE),
        (r"skip ci", re.IGNORECASE),
    ]
    for pattern, flags in checks:
        if re.search(pattern, line.strip(), flags):
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
    force_full_history: bool = False,
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
        force_full_history: If True, collect ALL changes from the beginning
            of the repo (ignores previous tags). Used for version resets.

    Returns:
        CollectedChanges with deduplicated, cleaned change lines.
    """
    result = CollectedChanges()

    # Find previous tag (skip if forcing full history for version reset)
    if force_full_history:
        result.previous_tag = None
        logger.info("Force full history: collecting ALL changes from the beginning")
    else:
        result.previous_tag = find_previous_tag(owner, repo, token, tag)
    logger.info("Previous tag: %s", result.previous_tag or "(none — first release)")

    pr_lines: list[str] = []
    commit_lines: list[str] = []

    # Source A: PR titles from auto-generated release notes
    try:
        notes_body = generate_release_notes(owner, repo, tag, result.previous_tag, token)
        for line in notes_body.split("\n"):
            if line.startswith("* "):
                raw_pr = line[2:].strip()
                if not _is_noise(raw_pr):
                    pr_lines.append(_clean_line(line, owner=owner, repo=repo))
        result.pr_count = len(pr_lines)
        logger.info("PR lines collected: %d", result.pr_count)
    except Exception as e:
        logger.warning("generateReleaseNotes failed: %s", e)

    # Source B: Direct commit messages
    base_ref = result.previous_tag
    if not base_ref:
        # No previous tag — compare from the first commit in the repo
        try:
            import subprocess
            first_commit_result = subprocess.run(
                ["git", "rev-list", "--max-parents=0", "HEAD"],
                capture_output=True, text=True, check=True,
            )
            base_ref = first_commit_result.stdout.strip().split("\n")[0]
            logger.info("No previous tag — using first commit: %s", base_ref[:12])
        except Exception as e:
            logger.warning("Could not find first commit: %s", e)
    if base_ref:
        try:
            commits = compare_commits(owner, repo, base_ref, "HEAD", token)
            for c in commits:
                msg = c["commit"]["message"].split("\n")[0].strip()
                author_login = (c.get("author") or {}).get("login") or ""
                # Skip automated bot commits
                if "bot" in author_login.lower() or "github-actions" in author_login.lower():
                    continue
                if not _is_noise(msg):
                    cleaned = _clean_line(msg, author_login=author_login if author_login else None, owner=owner, repo=repo)
                    commit_lines.append(cleaned)
            result.commit_count = len(commit_lines)
            logger.info("Commit lines collected: %d", result.commit_count)
        except Exception as e:
            logger.warning("compareCommits failed: %s", e)

    # Merge, deduplicate, and cap
    all_lines = _deduplicate([*pr_lines, *commit_lines])
    result.raw_lines = all_lines[:max_lines]
    logger.info("Total raw lines for AI: %d", len(result.raw_lines))

    return result
