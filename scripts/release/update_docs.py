"""
Documentation and release JSON updater for the GEMMA release pipeline.

Handles:
- CHANGELOG.md (Keep a Changelog format)
- docs/user-guide/changelog.md (VitePress format)
- docs/user-guide/public/releases.json (full release history)
- docs/user-guide/public/latest.json (stable release pointer)
- docs/user-guide/public/latest-beta.json (preview release pointer)
- docs/user-guide/index.md (homepage download link)

Extracted from gemma-plugin.yml lines 348–617.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from scripts.utils.changelog import (
    format_keep_a_changelog,
    format_vitepress_changelog,
    format_date_display,
    insert_changelog_section,
)
from scripts.utils.files import read_text, write_text, ensure_dir
from scripts.utils.github import get_contributors

logger = logging.getLogger(__name__)

# Base paths (relative to repo root)
CHANGELOG_PATH = "CHANGELOG.md"
DOCS_CHANGELOG_PATH = "docs/user-guide/changelog.md"
INDEX_MD_PATH = "docs/user-guide/index.md"
PUBLIC_DIR = "docs/user-guide/public"
RELEASES_JSON_PATH = f"{PUBLIC_DIR}/releases.json"
LATEST_JSON_PATH = f"{PUBLIC_DIR}/latest.json"
LATEST_BETA_JSON_PATH = f"{PUBLIC_DIR}/latest-beta.json"


def update_changelogs(
    version: str,
    date: str,
    changes: dict[str, list[str]],
    contributors: list[str] | None = None,
) -> None:
    """Update both CHANGELOG.md and docs/user-guide/changelog.md.

    Args:
        version: Version string (e.g. "1.5.0").
        date: ISO date string (e.g. "2026-07-22").
        changes: Structured changes dict with categories.
        contributors: List of GitHub usernames. Uses git log if None.
    """
    if contributors is None:
        contributors = get_contributors()

    date_display = format_date_display(date)

    # Update root CHANGELOG.md
    root_section = format_keep_a_changelog(version, date, changes)
    insert_changelog_section(CHANGELOG_PATH, root_section)

    # Update docs changelog
    docs_section = format_vitepress_changelog(version, date_display, changes, contributors)
    insert_changelog_section(DOCS_CHANGELOG_PATH, docs_section)


def update_index_md_download_link(
    version: str,
    tag: str,
    owner: str = "GMD-Repository",
    repo: str = "gemma-plugin",
) -> None:
    """Update the homepage download link in index.md to point to the latest version.

    Args:
        version: Version string (e.g. "1.5.0").
        tag: Git tag (e.g. "v1.5.0").
        owner: GitHub org/user.
        repo: GitHub repository name.
    """
    zip_name = f"gemma-plugin-{tag}.zip"
    download_url = f"https://github.com/{owner}/{repo}/releases/download/{tag}/{zip_name}"
    
    # Read current index.md
    content = read_text(INDEX_MD_PATH)
    if not content:
        logger.warning("⚠️  Could not read index.md")
        return
    
    # Replace the download link in the hero actions section
    # Pattern matches: link: https://github.com/.../releases/download/...
    pattern = r"(- theme: alt\s+text: Download\s+link: )https://github\.com/[^/]+/[^/]+/releases/download/[^\s]+"
    updated_content = re.sub(
        pattern,
        rf"\1{download_url}",
        content,
        flags=re.MULTILINE
    )
    
    if updated_content != content:
        write_text(INDEX_MD_PATH, updated_content)
        logger.info("✅ index.md download link updated to %s", tag)
    else:
        logger.warning("⚠️  Could not find download link pattern in index.md")


def update_latest_json(
    version: str,
    tag: str,
    date: str,
    owner: str = "GMD-Repository",
    repo: str = "gemma-plugin",
) -> None:
    """Write the latest.json file for the stable release channel.

    This file is consumed by the VitePress LatestReleaseCard component
    and the Layout.vue download URL rewriter.

    Args:
        version: Version string.
        tag: Git tag (e.g. "v1.5.0").
        date: ISO date string.
        owner: GitHub org/user.
        repo: GitHub repository name.
    """
    base_url = "https://gmd-repository.github.io/gemma-plugin"
    zip_name = f"gemma-plugin-{tag}.zip"

    data = {
        "version": version,
        "tag": tag,
        "releaseDate": date,
        "repositoryUrl": f"{base_url}/gemma.xml",
        "downloadUrl": f"https://github.com/{owner}/{repo}/releases/download/{tag}/{zip_name}",
        "releaseUrl": f"https://github.com/{owner}/{repo}/releases/tag/{tag}",
        "changelogUrl": f"{base_url}/changelog/{tag}",
    }

    ensure_dir(PUBLIC_DIR)
    write_text(LATEST_JSON_PATH, json.dumps(data, indent=2))
    logger.info("✅ latest.json generated")


def update_latest_beta_json(
    preview_version: str,
    revision: str,
    date: str,
    preview_owner: str = "GMD-Repository",
    preview_repo: str = "gemma-plugin-preview",
) -> None:
    """Write the latest-beta.json file for the preview release channel.

    Args:
        preview_version: Preview version string (e.g. "1.0.0-r160").
        revision: Revision tag (e.g. "r160").
        date: ISO date string.
        preview_owner: GitHub org/user for preview repo.
        preview_repo: GitHub repository name for previews.
    """
    base_url = "https://gmd-repository.github.io/gemma-plugin"
    zip_name = f"gemma-plugin-{revision}.zip"

    data = {
        "version": preview_version,
        "tag": revision,
        "releaseDate": date,
        "repositoryUrl": f"{base_url}/gemma-beta.xml",
        "downloadUrl": f"https://github.com/{preview_owner}/{preview_repo}/releases/download/{revision}/{zip_name}",
        "releaseUrl": f"https://github.com/{preview_owner}/{preview_repo}/releases/tag/{revision}",
        "changelogUrl": f"{base_url}/changelog/{revision}",
    }

    ensure_dir(PUBLIC_DIR)
    write_text(LATEST_BETA_JSON_PATH, json.dumps(data, indent=2))
    logger.info("✅ latest-beta.json generated")


def update_releases_json(
    version: str,
    tag: str,
    date: str,
    changes: dict[str, list[str]],
    contributors: list[str] | None = None,
    prerelease: bool = False,
    owner: str = "GMD-Repository",
    repo: str = "gemma-plugin",
) -> None:
    """Update the releases.json file with a new release entry.

    This file contains the complete release history and is consumed
    by VitePress for the releases list page.

    Args:
        version: Version string.
        tag: Git tag.
        date: ISO date string.
        changes: Structured changes dict.
        contributors: List of GitHub usernames.
        prerelease: Whether this is a pre-release.
        owner: GitHub org/user.
        repo: GitHub repository name.
    """
    if contributors is None:
        contributors = get_contributors()

    zip_name = f"gemma-plugin-{tag}.zip"

    # Load existing releases.json
    releases_data = {"latest": version, "releases": []}
    existing_content = read_text(RELEASES_JSON_PATH)
    if existing_content:
        try:
            releases_data = json.loads(existing_content)
        except json.JSONDecodeError:
            logger.warning("⚠️  Could not parse existing releases.json, starting fresh")

    # Build new release entry
    new_release = {
        "version": version,
        "date": date,
        "tag": tag,
        "prerelease": prerelease,
        "contributors": contributors,
        "downloadUrl": f"https://github.com/{owner}/{repo}/releases/download/{tag}/{zip_name}",
        "releaseUrl": f"https://github.com/{owner}/{repo}/releases/tag/{tag}",
        "qgisVersions": ["3.34", "3.40", "3.44"],
        "changes": {
            "features": changes.get("features", []),
            "improvements": changes.get("improvements", []),
            "changes": changes.get("changes", []),
            "fixes": changes.get("fixes", []),
            "breaking": changes.get("breaking_changes", []),
            "deprecated": changes.get("deprecated", []),
            "dependencies": changes.get("dependencies", []),
        },
    }

    # Remove existing entry for this version and prepend new one
    releases_data["releases"] = [
        r for r in releases_data.get("releases", []) if r.get("version") != version
    ]
    releases_data["releases"].insert(0, new_release)
    releases_data["latest"] = version

    ensure_dir(PUBLIC_DIR)
    write_text(RELEASES_JSON_PATH, json.dumps(releases_data, indent=2))
    logger.info("✅ releases.json updated (%d releases)", len(releases_data["releases"]))
