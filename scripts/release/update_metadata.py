"""
metadata.txt version resolution and changelog update for the GEMMA release pipeline.

Handles:
- Reading the current version from metadata.txt
- Resolving the final version based on bump type / custom version
- Updating the version= field
- Prepending a new changelog entry to the changelog= field

Extracted from gemma-plugin.yml lines 38–99 and 320–345.
"""

from __future__ import annotations

import re
import logging
from pathlib import Path

from scripts.utils.version import bump_version, strip_prerelease, has_prerelease
from scripts.utils.files import read_metadata_raw, write_metadata_raw

logger = logging.getLogger(__name__)


def resolve_version(
    metadata_path: str | Path,
    bump_type: str = "auto",
    custom_version: str = "",
) -> tuple[str, str]:
    """Resolve the final release version from metadata.txt.

    Logic:
    - If custom_version is provided, use it (strip leading 'v').
    - If bump_type is major/minor/patch, bump the current version.
    - If bump_type is "auto" and version has a pre-release suffix, strip it.
    - If bump_type is "auto" and version is stable, use as-is.

    Also updates metadata.txt if the version changed.

    Args:
        metadata_path: Path to metadata.txt.
        bump_type: One of "auto", "major", "minor", "patch".
        custom_version: Optional manual version override.

    Returns:
        Tuple of (version, tag) e.g. ("1.5.0", "v1.5.0").

    Raises:
        ValueError: If version cannot be found in metadata.txt.
    """
    path = Path(metadata_path)
    content = read_metadata_raw(path)

    # Read current version
    version_match = re.search(r"^version=(\S+)", content, re.MULTILINE)
    if not version_match:
        raise ValueError(f"Could not find version= in {metadata_path}")

    current_version = version_match.group(1).strip()
    logger.info("Current version in metadata.txt: %s", current_version)

    # Resolve final version
    final_version = current_version
    custom_version = custom_version.strip()

    if custom_version:
        final_version = custom_version.lstrip("v")
        logger.info("Using custom version input: %s", final_version)

    elif bump_type != "auto":
        final_version = bump_version(current_version, bump_type)
        logger.info("Bumping version (%s): %s -> %s", bump_type, current_version, final_version)

    else:
        # Auto mode: strip pre-release suffix if present
        if has_prerelease(current_version):
            final_version = strip_prerelease(current_version)
            logger.info("Promoting to stable release: %s -> %s", current_version, final_version)
        else:
            logger.info("Using current stable version: %s", final_version)

    # Update metadata.txt if version changed
    if current_version != final_version:
        updated = re.sub(
            r"^version=\S+",
            f"version={final_version}",
            content,
            flags=re.MULTILINE,
        )
        write_metadata_raw(path, updated)
        logger.info("✅ metadata.txt updated with version: %s", final_version)

    tag = f"v{final_version}"
    return final_version, tag


def update_metadata_changelog(
    metadata_path: str | Path,
    version: str,
    highlights: list[str],
) -> None:
    """Prepend a new changelog entry to the changelog= field in metadata.txt.

    The changelog field format is:
        changelog=1.5.0: Item 1; Item 2; Item 3
            1.4.0: Previous items...

    Args:
        metadata_path: Path to metadata.txt.
        version: Version string (e.g. "1.5.0").
        highlights: List of changelog items.
    """
    path = Path(metadata_path)
    content = read_metadata_raw(path)

    # Build new changelog entry
    new_entry = f"{version}: {'; '.join(highlights)}"

    # Find and update the changelog= line
    changelog_match = re.search(r"^(changelog=)(.*)$", content, re.MULTILINE)

    if changelog_match:
        existing = changelog_match.group(2).strip()
        updated_changelog = f"{new_entry}\n    {existing}"
        content = re.sub(
            r"^changelog=.*$",
            f"changelog={updated_changelog}",
            content,
            flags=re.MULTILINE,
        )
    else:
        # No changelog field — add one after the about= block
        content = re.sub(
            r"^(about=.*)$",
            rf"\1\n\nchangelog={new_entry}",
            content,
            flags=re.MULTILINE,
        )

    write_metadata_raw(path, content)
    logger.info("✅ metadata.txt changelog updated for v%s", version)
