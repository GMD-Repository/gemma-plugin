"""
Rule-based changelog generation for the GEMMA release pipeline.

Replaced AI-powered generation (GitHub Models API — discontinued) with a
deterministic, conventional-commit-aware categorizer. Raw commit/PR lines
collected by collect_changes() are classified into structured categories
using prefix matching and keyword heuristics.

No external API calls are made. Fallback behaviour is preserved.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field

from scripts.utils.changelog import highlights_to_changes

logger = logging.getLogger(__name__)

# Generic fallback when no changes are found at all
GENERIC_FALLBACK = {
    "summary": "This release includes internal updates and maintenance improvements.",
    "features": [],
    "improvements": [
        "Improved overall plugin stability and performance",
        "Applied internal updates and maintenance fixes",
    ],
    "fixes": [],
    "documentation": [],
    "breaking_changes": [],
}

# Conventional commit prefix → changelog category mapping
_PREFIX_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^feat[!?(]", re.IGNORECASE), "features"),
    (re.compile(r"^fix[!?(]", re.IGNORECASE), "fixes"),
    (re.compile(r"^docs?[!?(]", re.IGNORECASE), "documentation"),
    (re.compile(r"^refactor[!?(]", re.IGNORECASE), "improvements"),
    (re.compile(r"^perf[!?(]", re.IGNORECASE), "improvements"),
    (re.compile(r"^style[!?(]", re.IGNORECASE), "improvements"),
    (re.compile(r"^test[!?(]", re.IGNORECASE), "improvements"),
    (re.compile(r"^BREAKING[!? ]", re.IGNORECASE), "breaking_changes"),
]

# Keyword heuristics for lines without conventional commit prefixes
_KEYWORD_FEATURES = re.compile(
    r"\b(add(ed)?|new|introduc|implement|creat|support)\b", re.IGNORECASE
)
_KEYWORD_FIXES = re.compile(
    r"\b(fix(ed)?|resolve(d)?|patch(ed)?|correct(ed)?|repair(ed)?|bug)\b",
    re.IGNORECASE,
)
_KEYWORD_DOCS = re.compile(
    r"\b(doc(s|umentation)?|readme|changelog|guide|vitepress)\b", re.IGNORECASE
)
_KEYWORD_BREAKING = re.compile(
    r"(breaking|BREAKING|break[s ])", re.IGNORECASE
)


@dataclass
class ChangelogResult:
    """Result of changelog generation."""

    summary: str = ""
    changes: dict[str, list[str]] = field(default_factory=dict)
    highlights: list[str] = field(default_factory=list)
    ai_generated: bool = False  # Always False — AI no longer used


def generate_changelog(
    version: str,
    raw_lines: list[str],
    ai_token: str = "",          # Kept for signature compatibility — unused
    prompt_path: str = "",       # Kept for signature compatibility — unused
) -> ChangelogResult:
    """Generate a changelog from raw change lines using rule-based categorization.

    Args:
        version: Version being released (e.g. "1.5.0").
        raw_lines: Raw change lines from collect_changes().
        ai_token: Unused (kept for backward-compatible call sites).
        prompt_path: Unused (kept for backward-compatible call sites).

    Returns:
        ChangelogResult with structured changes and a flat highlights list.
    """
    result = ChangelogResult()

    if not raw_lines:
        logger.warning("⚠️  No changes found — using generic fallback")
        result.changes = GENERIC_FALLBACK.copy()
        result.summary = GENERIC_FALLBACK["summary"]
        result.highlights = _flatten_changes(result.changes)
        return result

    result = _categorize(raw_lines)

    # Ensure we always have at least some highlights
    if not result.highlights:
        result.changes = GENERIC_FALLBACK.copy()
        result.summary = GENERIC_FALLBACK["summary"]
        result.highlights = _flatten_changes(result.changes)

    logger.info(
        "✅ Rule-based changelog: %d items (features=%d fixes=%d improvements=%d docs=%d breaking=%d)",
        len(result.highlights),
        len(result.changes.get("features", [])),
        len(result.changes.get("fixes", [])),
        len(result.changes.get("improvements", [])),
        len(result.changes.get("documentation", [])),
        len(result.changes.get("breaking_changes", [])),
    )
    return result


# ── Internal helpers ──────────────────────────────────────────────────────────


def _categorize(raw_lines: list[str]) -> ChangelogResult:
    """Classify raw lines into changelog categories using heuristics."""
    buckets: dict[str, list[str]] = {
        "features": [],
        "improvements": [],
        "fixes": [],
        "documentation": [],
        "breaking_changes": [],
    }

    for line in raw_lines:
        category = _classify_line(line)
        buckets[category].append(line)

    highlights = _flatten_changes(buckets)

    # Build a one-sentence summary from dominant category
    summary = _build_summary(buckets)

    return ChangelogResult(
        summary=summary,
        changes=buckets,
        highlights=highlights,
        ai_generated=False,
    )


def _classify_line(line: str) -> str:
    """Return the best-matching changelog category for a raw change line."""
    # Check conventional commit prefix first (most reliable)
    for pattern, category in _PREFIX_MAP:
        if pattern.search(line):
            return category

    # Fall back to keyword heuristics
    if _KEYWORD_BREAKING.search(line):
        return "breaking_changes"
    if _KEYWORD_FIXES.search(line):
        return "fixes"
    if _KEYWORD_FEATURES.search(line):
        return "features"
    if _KEYWORD_DOCS.search(line):
        return "documentation"

    # Default: general improvement
    return "improvements"


def _flatten_changes(changes: dict[str, list[str]]) -> list[str]:
    """Flatten a structured changes dict into a flat list of highlights."""
    highlights: list[str] = []
    for key in ["features", "improvements", "fixes", "documentation", "breaking_changes"]:
        highlights.extend(changes.get(key, []))
    return highlights


def _build_summary(buckets: dict[str, list[str]]) -> str:
    """Build a short release summary sentence from bucket sizes."""
    parts: list[str] = []
    if buckets.get("features"):
        n = len(buckets["features"])
        parts.append(f"{n} new feature{'s' if n > 1 else ''}")
    if buckets.get("fixes"):
        n = len(buckets["fixes"])
        parts.append(f"{n} bug fix{'es' if n > 1 else ''}")
    if buckets.get("improvements"):
        n = len(buckets["improvements"])
        parts.append(f"{n} improvement{'s' if n > 1 else ''}")
    if buckets.get("documentation"):
        parts.append("documentation updates")
    if buckets.get("breaking_changes"):
        parts.append("breaking changes")

    if not parts:
        return GENERIC_FALLBACK["summary"]

    return "This release includes " + ", ".join(parts) + "."
