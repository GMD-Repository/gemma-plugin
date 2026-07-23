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
    target_commitish: str | None = None,
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
        target_commitish: Target branch for the release tag. Defaults to None (uses repo default branch).
        release_name: Custom release name. Defaults to "GEMMA Plugin v{version}".

    Returns:
        ReleaseResult with the release URL and ID.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    name = release_name or f"GEMMA Plugin v{version}"

    # Build release body
    if prerelease or "Preview" in name:
        body = _build_preview_body(version, highlights, tag)
    else:
        body = _build_stable_body(version, highlights)

    # Create the release
    logger.info("Creating GitHub Release: %s (prerelease=%s)", name, prerelease)

    payload: dict[str, Any] = {
        "tag_name": tag,
        "name": name,
        "body": body,
        "draft": False,
        "prerelease": prerelease,
        "make_latest": "true" if not prerelease else "false",
    }
    if target_commitish:
        payload["target_commitish"] = target_commitish

    create_resp = requests.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/releases",
        headers=headers,
        json=payload,
        timeout=30,
    )

    if create_resp.status_code == 422 and "already_exists" in create_resp.text:
        logger.warning("Release or tag '%s' already exists on %s/%s. Fetching existing release...", tag, owner, repo)
        get_resp = requests.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/releases/tags/{tag}",
            headers=headers,
            timeout=30,
        )
        if get_resp.ok:
            release_data = get_resp.json()
            release_url = release_data["html_url"]
            release_id = release_data["id"]
            logger.info("✅ Found existing release: %s (ID: %s)", release_url, release_id)
        else:
            logger.error("Failed to fetch existing release (%d): %s", get_resp.status_code, get_resp.text)
            create_resp.raise_for_status()
    else:
        if not create_resp.ok:
            logger.error("Failed to create GitHub release (%d): %s", create_resp.status_code, create_resp.text)
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
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    zip_name = zip_path.name
    file_size = zip_path.stat().st_size

    logger.info("Uploading release asset: %s (%d bytes)", zip_name, file_size)

    # Delete existing asset with same name if present
    rel_resp = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/releases/{release_id}",
        headers=headers,
        timeout=30,
    )
    if rel_resp.ok:
        assets = rel_resp.json().get("assets", [])
        for asset in assets:
            if asset.get("name") == zip_name:
                asset_id = asset.get("id")
                logger.info("Deleting existing asset %s (ID: %s)...", zip_name, asset_id)
                del_resp = requests.delete(
                    f"{GITHUB_API}/repos/{owner}/{repo}/releases/assets/{asset_id}",
                    headers=headers,
                    timeout=30,
                )
                if not del_resp.ok:
                    logger.warning("Failed to delete existing asset: %s", del_resp.text)

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

    if not upload_resp.ok:
        logger.error("Failed to upload release asset (%d): %s", upload_resp.status_code, upload_resp.text)
    upload_resp.raise_for_status()
    asset_data = upload_resp.json()
    asset_url = asset_data.get("browser_download_url", "")
    logger.info("✅ ZIP uploaded as release asset: %s", zip_name)

    return asset_url


def prune_old_releases(
    owner: str,
    repo: str,
    token: str,
    keep_count: int = 10,
) -> None:
    """Delete older GitHub releases and their associated tags, keeping only the latest `keep_count` releases.

    Args:
        owner: Repository owner.
        repo: Repository name.
        token: GitHub API token.
        keep_count: Number of latest releases to retain (default: 10).
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    url = f"{GITHUB_API}/repos/{owner}/{repo}/releases?per_page=100"
    resp = requests.get(url, headers=headers, timeout=30)
    if not resp.ok:
        logger.warning("Could not fetch releases for cleanup: %s", resp.text)
        return

    releases = resp.json()
    if len(releases) <= keep_count:
        logger.info("Found %d releases (<= %d limit). No cleanup needed.", len(releases), keep_count)
        return

    releases_to_delete = releases[keep_count:]
    logger.info("Pruning %d old release(s), retaining latest %d...", len(releases_to_delete), keep_count)

    for rel in releases_to_delete:
        rel_id = rel["id"]
        tag_name = rel.get("tag_name", "")
        rel_name = rel.get("name", tag_name)

        # Delete release
        del_resp = requests.delete(f"{GITHUB_API}/repos/{owner}/{repo}/releases/{rel_id}", headers=headers, timeout=30)
        if del_resp.status_code in (204, 404):
            logger.info("Deleted release %s (ID: %s)", rel_name, rel_id)
        else:
            logger.warning("Failed to delete release %s: %s", rel_name, del_resp.text)

        # Delete git ref tag
        if tag_name:
            tag_resp = requests.delete(
                f"{GITHUB_API}/repos/{owner}/{repo}/git/refs/tags/{tag_name}",
                headers=headers,
                timeout=30,
            )
            if tag_resp.status_code in (204, 404):
                logger.info("Deleted tag %s", tag_name)
            else:
                logger.warning("Failed to delete tag %s: %s", tag_name, tag_resp.text)

