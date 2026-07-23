"""
QGIS plugin ZIP builder for the GEMMA release pipeline.

Creates a QGIS-compliant plugin ZIP with a gemma-plugin/ root folder,
excluding CI/CD files, docs, and other non-plugin artifacts.

Extracted from gemma-plugin.yml lines 378–407 and deploy-preview.yml lines 44–93.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from scripts.utils.files import read_metadata_raw, write_metadata_raw

logger = logging.getLogger(__name__)

# Patterns to exclude from the plugin ZIP
EXCLUDE_PATTERNS = [
    ".git",
    ".git/*",
    ".github",
    ".github/*",
    ".agents",
    ".agents/*",
    ".antigravity*",
    "docs",
    "docs/*",
    "scripts",
    "scripts/*",
    "node_modules",
    "node_modules/*",
    "__pycache__",
    "__pycache__/*",
    "*.pyc",
    "*.zip",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "tsconfig*.json",
    ".gitignore",
    "README.md",
]


def build_plugin_zip(
    version: str,
    output_name: str,
    source_dir: str = ".",
    is_preview: bool = False,
    preview_revision: str | None = None,
    preview_branch: str | None = None,
) -> Path:
    """Build a QGIS-compliant plugin ZIP file.

    The ZIP contains a gemma-plugin/ root folder with all plugin files.
    For preview builds, metadata.txt inside the ZIP is modified to set
    name="GEMMA (Beta)" and version="{base}-r{N}".

    Args:
        version: Version string for the ZIP name.
        output_name: Name of the output ZIP file.
        source_dir: Root directory of the plugin source.
        is_preview: If True, modify metadata inside ZIP for preview builds.
        preview_revision: Revision string (e.g. "r160") for preview builds.
        preview_branch: Branch name for preview changelog entry.

    Returns:
        Path to the created ZIP file.
    """
    source = Path(source_dir).resolve()
    output_path = source / output_name

    # Clean up any existing output
    if output_path.exists():
        output_path.unlink()

    # Create a temporary directory for staging
    with tempfile.TemporaryDirectory(prefix="gemma_plugin_") as tmp_dir:
        plugin_dir = Path(tmp_dir) / "gemma-plugin"
        plugin_dir.mkdir()

        logger.info("Staging plugin files to %s", plugin_dir)

        # Copy files, respecting exclusion patterns
        _copy_plugin_files(source, plugin_dir)

        # For preview builds, modify the metadata inside the staged directory
        if is_preview and preview_revision:
            _modify_preview_metadata(
                plugin_dir / "metadata.txt",
                preview_revision,
                preview_branch or "main",
            )

        # Create the ZIP from the temporary directory
        logger.info("Creating ZIP: %s", output_name)
        _create_zip(tmp_dir, output_path)

    logger.info("✅ Plugin ZIP created: %s", output_path.name)
    return output_path


def _copy_plugin_files(source: Path, dest: Path) -> None:
    """Copy plugin files from source to destination, excluding non-plugin files."""
    for item in source.iterdir():
        if _should_exclude(item, source):
            continue

        dest_item = dest / item.name
        if item.is_dir():
            shutil.copytree(
                item,
                dest_item,
                ignore=shutil.ignore_patterns(*EXCLUDE_PATTERNS),
            )
        else:
            shutil.copy2(item, dest_item)


def _should_exclude(path: Path, root: Path) -> bool:
    """Check if a file/directory should be excluded from the ZIP."""
    name = path.name
    rel_path = str(path.relative_to(root))

    for pattern in EXCLUDE_PATTERNS:
        # Handle glob-style patterns
        if "*" in pattern:
            import fnmatch
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel_path, pattern):
                return True
        else:
            if name == pattern or rel_path == pattern:
                return True

    return False


def _create_zip(staging_dir: str, output_path: Path) -> None:
    """Create a ZIP file from the staging directory.

    Uses the system `zip` command on Linux (CI) or Python's shutil on Windows.
    """
    try:
        # Try using system zip command (available on ubuntu-latest CI runners)
        subprocess.run(
            ["zip", "-r", str(output_path), "gemma-plugin/"],
            cwd=staging_dir,
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        # Fallback to Python's shutil.make_archive
        logger.info("System 'zip' not found — using Python shutil")
        shutil.make_archive(
            str(output_path).replace(".zip", ""),
            "zip",
            root_dir=staging_dir,
            base_dir="gemma-plugin",
        )


def _modify_preview_metadata(
    metadata_path: Path,
    revision: str,
    branch: str,
) -> None:
    """Modify metadata.txt inside the staged plugin for preview builds.

    Changes:
    - name → "GEMMA (Beta)"
    - version → "{base_version}-{revision}"
    - Prepends preview changelog entry
    """
    if not metadata_path.exists():
        logger.warning("metadata.txt not found in staged plugin — skipping modification")
        return

    content = read_metadata_raw(metadata_path)

    # Extract base version
    version_match = re.search(r"^version=(.*)", content, re.MULTILINE)
    base_version = version_match.group(1).strip() if version_match else "0.0.0"
    preview_version = f"{base_version}-{revision}"

    # Get latest commit message for changelog
    commit_msg = "Automated preview release"
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%s"],
            capture_output=True,
            text=True,
            check=True,
        )
        commit_msg = result.stdout.strip() or commit_msg
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Update fields
    content = re.sub(r"^name=.*$", "name=GEMMA (Beta)", content, flags=re.MULTILINE)
    content = re.sub(r"^version=.*$", f"version={preview_version}", content, flags=re.MULTILINE)

    # Prepend preview changelog entry
    preview_entry = f"{preview_version}: Preview build {revision} [{branch}] - {commit_msg}"
    content = re.sub(
        r"^changelog=",
        f"changelog={preview_entry}\n    ",
        content,
        flags=re.MULTILINE,
    )

    write_metadata_raw(metadata_path, content)
    logger.info("✅ Staged metadata.txt updated: name=GEMMA (Beta), version=%s", preview_version)
