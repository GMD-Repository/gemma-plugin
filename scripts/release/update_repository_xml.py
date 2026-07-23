"""
QGIS repository XML file updater for the GEMMA release pipeline.

Generates gemma.xml (stable) and gemma-beta.xml (preview) files
in docs/user-guide/public/ for serving via GitHub Pages.

Extracted from gemma-plugin.yml lines 511–542 and deploy-preview.yml lines 182–211.
"""

from __future__ import annotations

import logging
from pathlib import Path

from scripts.utils.files import read_metadata, write_text, ensure_dir
from scripts.utils.xml_builder import build_plugin_xml

logger = logging.getLogger(__name__)

# Output paths (relative to repo root)
PUBLIC_DIR = "docs/user-guide/public"
STABLE_XML_PATH = f"{PUBLIC_DIR}/gemma.xml"
BETA_XML_PATH = f"{PUBLIC_DIR}/gemma-beta.xml"


def update_stable_xml(
    metadata_path: str,
    version: str,
    tag: str,
    owner: str = "GMD-Repository",
    repo: str = "gemma-plugin",
) -> None:
    """Generate gemma.xml for the stable production channel.

    Args:
        metadata_path: Path to metadata.txt.
        version: Version string (e.g. "1.5.0").
        tag: Git tag (e.g. "v1.5.0").
        owner: GitHub org/user.
        repo: GitHub repository name.
    """
    from datetime import date

    metadata = read_metadata(metadata_path)
    zip_name = f"gemma-plugin-{tag}.zip"
    download_url = f"https://github.com/{owner}/{repo}/releases/download/{tag}/{zip_name}"
    today = date.today().isoformat()

    xml_content = build_plugin_xml(
        metadata=metadata,
        version=version,
        download_url=download_url,
        date=today,
        is_beta=False,
        owner=owner,
        repo=repo,
    )

    ensure_dir(PUBLIC_DIR)
    write_text(STABLE_XML_PATH, xml_content)
    logger.info("✅ gemma.xml generated (Production channel)")


def update_beta_xml(
    metadata_path: str,
    preview_version: str,
    revision: str,
    zip_name: str,
    preview_owner: str = "GMD-Repository",
    preview_repo: str = "gemma-plugin-preview",
    source_owner: str = "GMD-Repository",
    source_repo: str = "gemma-plugin",
) -> None:
    """Generate gemma-beta.xml for the preview/beta channel.

    Args:
        metadata_path: Path to metadata.txt.
        preview_version: Preview version string (e.g. "1.0.0-r160").
        revision: Revision tag (e.g. "r160").
        zip_name: Name of the preview ZIP file.
        preview_owner: GitHub org for preview releases.
        preview_repo: GitHub repo for preview releases.
        source_owner: GitHub org for the main repository (used for tracker/repo links).
        source_repo: GitHub repo name for the main repository.
    """
    from datetime import date

    metadata = read_metadata(metadata_path)
    download_url = f"https://github.com/{preview_owner}/{preview_repo}/releases/download/{revision}/{zip_name}"
    today = date.today().isoformat()

    xml_content = build_plugin_xml(
        metadata=metadata,
        version=preview_version,
        download_url=download_url,
        date=today,
        is_beta=True,
        owner=source_owner,
        repo=source_repo,
    )

    ensure_dir(PUBLIC_DIR)
    write_text(BETA_XML_PATH, xml_content)
    logger.info("✅ gemma-beta.xml generated (Beta channel)")
    logger.info("   Download URL: %s", download_url)
    logger.info("   Version: %s", preview_version)
