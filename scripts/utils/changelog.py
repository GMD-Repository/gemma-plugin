"""
Markdown changelog formatting utilities for the GEMMA release pipeline.

Handles formatting changelog entries for:
- CHANGELOG.md (Keep a Changelog format)
- docs/user-guide/changelog.md (VitePress format with <Contributors> component)
- Inserting new sections into existing changelog files
"""

from __future__ import annotations

import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Default contributor list for the VitePress changelog
DEFAULT_CONTRIBUTORS = [
    "kentemman-gmd",
    "velascojasper0",
    "psacjperez",
    "tatsmenot",
    "pacoleslaw",
    "nbacquiano-ui",
]


def format_keep_a_changelog(
    version: str,
    date: str,
    changes: dict[str, list[str]],
) -> str:
    """Format a changelog entry in Keep a Changelog style.

    Args:
        version: Version string (e.g. "1.5.0").
        date: ISO date string (e.g. "2026-07-22").
        changes: Dict with keys like "features", "improvements", "fixes", etc.

    Returns:
        Formatted markdown section ready to insert into CHANGELOG.md.
    """
    lines = [f"## [{version}] - {date}", ""]

    # Map change categories to Keep a Changelog section headers
    section_map = {
        "features": "Added",
        "improvements": "Changed",
        "fixes": "Fixed",
        "breaking_changes": "Removed",
        "documentation": "Documentation",
        "deprecated": "Deprecated",
    }

    for key, header in section_map.items():
        items = changes.get(key, [])
        if items:
            lines.append(f"### {header}")
            for item in items:
                lines.append(f"- {item}")
            lines.append("")

    # If no categorized changes, put all highlights under "Added"
    if not any(changes.get(k, []) for k in section_map):
        all_items = []
        for items_list in changes.values():
            all_items.extend(items_list)
        if all_items:
            lines.append("### Added")
            for item in all_items:
                lines.append(f"- {item}")
            lines.append("")

    return "\n".join(lines) + "\n"


def format_vitepress_changelog(
    version: str,
    date_display: str,
    changes: dict[str, list[str]],
    contributors: list[str] | None = None,
) -> str:
    """Format a changelog entry for the VitePress docs site.

    Args:
        version: Version string (e.g. "1.5.0").
        date_display: Human-readable date (e.g. "Jul 22, 2026").
        changes: Dict with keys like "features", "improvements", "fixes", etc.
        contributors: List of GitHub usernames. Uses defaults if None.

    Returns:
        Formatted markdown section for docs/user-guide/changelog.md.
    """
    if contributors is None:
        contributors = DEFAULT_CONTRIBUTORS

    lines = [f"## {version}", f"<time>{date_display}</time>", ""]

    # Map categories to display headers with emoji
    section_map = {
        "features": "✨ New Features",
        "improvements": "⚡ Improvements & Fixes",
        "fixes": "🐛 Bug Fixes",
        "breaking_changes": "💥 Breaking Changes",
        "documentation": "📚 Documentation",
        "deprecated": "🗑️ Deprecated",
    }

    has_content = False
    for key, header in section_map.items():
        items = changes.get(key, [])
        if items:
            lines.append(f"### {header}")
            for item in items:
                lines.append(f"- {item}")
            lines.append("")
            has_content = True

    # Fallback: if no categorized changes, dump everything under New Features
    if not has_content:
        all_items = []
        for items_list in changes.values():
            all_items.extend(items_list)
        if all_items:
            lines.append("### ✨ New Features")
            for item in all_items:
                lines.append(f"- {item}")
            lines.append("")

    # Add Contributors component
    contrib_list = str(contributors)
    lines.append(f"<Contributors :contributors=\"{contrib_list}\" />")
    lines.append("")

    return "\n".join(lines) + "\n"


def insert_changelog_section(filepath: str | Path, new_section: str) -> None:
    """Insert a new changelog section at the top of an existing changelog file.

    Finds the first version heading (## ...) and inserts the new section
    before it. If no existing section is found, appends to the end.

    Args:
        filepath: Path to the changelog markdown file.
        new_section: The formatted markdown section to insert.
    """
    path = Path(filepath)
    if not path.exists():
        logger.warning("Changelog file not found: %s — creating new file", path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_section, encoding="utf-8")
        return

    content = path.read_text(encoding="utf-8")

    # Find the first version section heading (## [1.0.0] or ## 1.0.0)
    match = re.search(r"^## [\[\d]", content, re.MULTILINE)

    if match:
        insert_pos = match.start()
        updated = content[:insert_pos] + new_section + content[insert_pos:]
    else:
        updated = content + "\n\n" + new_section

    path.write_text(updated, encoding="utf-8")
    logger.info("✅ %s updated with new release section", path)


def format_date_display(iso_date: str) -> str:
    """Convert an ISO date string to a human-readable format.

    Example: "2026-07-22" -> "Jul 22, 2026"
    """
    from datetime import datetime

    dt = datetime.strptime(iso_date, "%Y-%m-%d")
    return dt.strftime("%b %d, %Y")


def highlights_to_changes(highlights: list[str]) -> dict[str, list[str]]:
    """Categorize a flat list of highlights into structured change categories.

    Used as a fallback when the AI returns a flat list instead of structured JSON.
    Categorizes based on the leading verb:
    - Added/New -> features
    - Improved/Enhanced/Optimized -> improvements
    - Fixed/Resolved -> fixes

    Args:
        highlights: Flat list of changelog items.

    Returns:
        Dict with categorized changes.
    """
    features: list[str] = []
    improvements: list[str] = []
    fixes: list[str] = []

    for item in highlights:
        lower = item.lower().strip()
        if lower.startswith(("fixed", "resolved", "bug")):
            fixes.append(item)
        elif lower.startswith(("improved", "enhanced", "optimized", "updated", "refactored")):
            improvements.append(item)
        else:
            features.append(item)

    return {
        "features": features,
        "improvements": improvements,
        "fixes": fixes,
    }
