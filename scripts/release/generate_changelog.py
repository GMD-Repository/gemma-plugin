"""
AI-powered changelog generation for the GEMMA release pipeline.

Uses GitHub Models API to transform raw commit/PR lines into
user-facing changelog highlights. Falls back gracefully to raw
lines if the AI call fails.

Extracted from gemma-plugin.yml lines 223–317.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from scripts.ai.github_models import call_github_model, parse_ai_json, load_prompt
from scripts.utils.changelog import highlights_to_changes

logger = logging.getLogger(__name__)

# Default path to the AI prompt file (relative to repo root)
DEFAULT_PROMPT_PATH = "scripts/ai/prompts/release_notes.md"

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


@dataclass
class ChangelogResult:
    """Result of AI changelog generation."""

    summary: str = ""
    changes: dict[str, list[str]] = field(default_factory=dict)
    highlights: list[str] = field(default_factory=list)
    ai_generated: bool = False


def generate_changelog(
    version: str,
    raw_lines: list[str],
    ai_token: str,
    prompt_path: str = DEFAULT_PROMPT_PATH,
) -> ChangelogResult:
    """Generate a changelog from raw change lines using AI.

    Args:
        version: Version being released (e.g. "1.5.0").
        raw_lines: Raw change lines from collect_changes().
        ai_token: GitHub token with models:read permission.
        prompt_path: Path to the AI system prompt file.

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

    # Try AI generation
    try:
        result = _generate_with_ai(version, raw_lines, ai_token, prompt_path)
    except Exception as e:
        logger.warning("⚠️  AI failed: %s", e)
        logger.info("Falling back to raw commit lines.")
        result = _fallback_to_raw(raw_lines)

    # Ensure we always have at least some highlights
    if not result.highlights:
        result.changes = GENERIC_FALLBACK.copy()
        result.summary = GENERIC_FALLBACK["summary"]
        result.highlights = _flatten_changes(result.changes)

    return result


def _generate_with_ai(
    version: str,
    raw_lines: list[str],
    ai_token: str,
    prompt_path: str,
) -> ChangelogResult:
    """Attempt to generate changelog via GitHub Models AI."""
    # Load the system prompt
    system_prompt = load_prompt(prompt_path)

    # Build the user prompt
    changes_list = "\n".join(f"- {line}" for line in raw_lines)
    user_prompt = (
        f"Summarize the following changes for GEMMA Plugin v{version}:\n\n"
        f"{changes_list}"
    )

    # Call the AI
    response = call_github_model(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        token=ai_token,
    )

    # Parse the response
    parsed = parse_ai_json(response.content)

    result = ChangelogResult(ai_generated=True)

    if isinstance(parsed, dict):
        # Structured JSON format (new format)
        result.summary = parsed.get("summary", "")
        result.changes = {
            "features": parsed.get("features", []),
            "improvements": parsed.get("improvements", []),
            "fixes": parsed.get("fixes", []),
            "documentation": parsed.get("documentation", []),
            "breaking_changes": parsed.get("breaking_changes", []),
        }
        result.highlights = _flatten_changes(result.changes)
    elif isinstance(parsed, list) and len(parsed) > 0:
        # Flat array format (legacy format — backward compatible)
        result.highlights = parsed
        result.changes = highlights_to_changes(parsed)
        result.summary = ""
    else:
        raise ValueError("AI returned empty or unexpected format")

    logger.info("✅ AI changelog: %d items (structured=%s)", len(result.highlights), isinstance(parsed, dict))
    return result


def _fallback_to_raw(raw_lines: list[str]) -> ChangelogResult:
    """Create a changelog result from raw commit lines as fallback."""
    highlights = raw_lines[:8]
    return ChangelogResult(
        summary="",
        changes=highlights_to_changes(highlights),
        highlights=highlights,
        ai_generated=False,
    )


def _flatten_changes(changes: dict[str, list[str]]) -> list[str]:
    """Flatten a structured changes dict into a flat list of highlights."""
    highlights: list[str] = []
    # Ordered categories for consistent output
    for key in ["features", "improvements", "fixes", "documentation", "breaking_changes"]:
        highlights.extend(changes.get(key, []))
    return highlights
