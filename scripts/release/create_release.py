"""
GitHub Release creation and asset upload for the GEMMA release pipeline.

Handles:
- Creating GitHub Releases (stable or pre-release)
- Uploading ZIP files as release assets

Extracted from gemma-plugin.yml lines 410–451 and deploy-preview.yml lines 95–148.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
GITHUB_UPLOAD_URL = "https://uploads.github.com"


@dataclass
class ReleaseResult:
    """Result of a GitHub Release creation."""

    html_url: str
    release_id: int
    asset_url: str = ""


def create_github_release(
    owner: str,
    repo: str,
    tag: str,
    version: str,
    highlights: list[str],
    zip_path: Path,
    token: str,
    prerelease: bool = False,
    target_commitish: str = "main",
    release_name: str | None = None,
) -> ReleaseResult:
    """Create a GitHub Release and upload the plugin ZIP as an asset.

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.
        tag: Git tag (e.g. "v1.5.0" or "r160").
        version: Version string for the release title.
        highlights: List of changelog items for the release body.
        zip_path: Path to the plugin ZIP file.
        token: GitHub API token.
        prerelease: Whether this is a pre-release.
        target_commitish: Target branch for the release tag.
        release_name: Custom release name. Defaults to "GEMMA Plugin v{version}".

    Returns:
        ReleaseResult with the release URL and ID.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Build release body
    if prerelease:
        body = _build_preview_body(version, highlights, tag)
    else:
        body = _build_stable_body(version, highlights)

    name = release_name or f"GEMMA Plugin v{version}"

    # Create the release
    logger.info("Creating GitHub Release: %s (prerelease=%s)", name, prerelease)

    create_resp = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/releases",
        headers=headers,
        json={
            "tag_name": tag,
            "target_commitish": target_commitish,
            "name": name,
            "body": body,
            "draft": False,
            "prerelease": prerelease,
            "make_latest": "true" if not prerelease else "false",
        },
        timeout=30,
    )
    create_resp.raise_for_status()
    release_data = create_resp.json()

    release_url = release_data["html_url"]
    release_id = release_data["id"]
    logger.info("✅ Release created: %s", release_url)

    # Upload the ZIP as a release asset
    asset_url = _upload_release_asset(
        owner=owner,
        repo=repo,
        release_id=release_id,
        zip_path=zip_path,
        token=token,
    )

    return ReleaseResult(
        html_url=release_url,
        release_id=release_id,
        asset_url=asset_url,
    )


def _build_stable_body(version: str, highlights: list[str]) -> str:
    """Build the release body for a stable release."""
    bullet_list = "\n".join(f"- {h}" for h in highlights)
    return "\n".join([
        f"## What's New in v{version}",
        "",
        bullet_list,
        "",
        "---",
        "**Installation:** Download the `.zip` file below and install in QGIS via "
        "*Plugins → Manage and Install Plugins → Install from ZIP*.",
    ])


def _build_preview_body(version: str, highlights: list[str], revision: str) -> str:
    """Build the release body for a preview release."""
    return "\n".join([
        f"## 🚀 GEMMA Preview Build ({revision})",
        "",
        f"Automated preview release for v{version}.",
        "",
        "### Installation:",
        "1. Download the ZIP file below.",
        "2. Open QGIS → **Plugins** → **Manage and Install Plugins** → **Install from ZIP**.",
        "3. Select the downloaded ZIP file and click **Install Plugin**.",
    ])


def _upload_release_asset(
    owner: str,
    repo: str,
    release_id: int,
    zip_path: Path,
    token: str,
) -> str:
    """Upload a ZIP file as a release asset.

    Returns:
        The browser download URL for the uploaded asset.
    """
    zip_name = zip_path.name
    file_size = zip_path.stat().st_size

    logger.info("Uploading release asset: %s (%d bytes)", zip_name, file_size)

    with open(zip_path, "rb") as f:
        upload_resp = requests.post(
            f"{GITHUB_UPLOAD_URL}/repos/{owner}/{repo}/releases/{release_id}/assets",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/zip",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            params={"name": zip_name},
            data=f,
            timeout=120,
        )

    upload_resp.raise_for_status()
    asset_data = upload_resp.json()
    asset_url = asset_data.get("browser_download_url", "")
    logger.info("✅ ZIP uploaded as release asset: %s", zip_name)

    return asset_url
