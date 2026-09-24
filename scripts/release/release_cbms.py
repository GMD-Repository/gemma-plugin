#!/usr/bin/env python3
"""
GEMMA Plugin — CBMS Closed Beta Release Pipeline Orchestrator

Standalone release script specifically for the cbms_main branch.
Called from GitHub Actions (.github/workflows/release-cbms-preview.yml) or locally with --dry-run.

Key behaviors:
1. Calculates revision number from git (HEAD count).
2. Sets version as {base_version}-cbms-{revision}.
3. Stages plugin into a 'gemma-cbmsbeta/' root folder.
4. Automatically patches:
   - metadata.txt (name="GEMMA (CBMS Beta)", version, experimental=True, changelog)
   - gmd_pipeline_provider.py (id='gmd_cbms_pipeline', name='GMD CBMS Pipeline')
   - gmd_pipeline.py (menu="Gemma (CBMS)", toolbar="Gemma CBMS Toolbar")
   - cbmsmv_dialog.py & createea dialog (algorithm provider ID alignment)
   to ensure seamless side-by-side coexistence in QGIS without conflicts.
5. Packages into gemma-cbmsbeta-{revision}.zip.
6. Publishes release on GMD-Repository/gemma-plugin-closed-preview with tag cbms-{revision}.
7. Prunes old CBMS releases (matching tag prefix "cbms-", retaining latest N).
8. Generates docs/user-guide/public/gemma-cbms.xml and docs/user-guide/public/latest-cbms.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape_impl

# Ensure the repo root is on the Python path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.utils.files import (
    set_github_output,
    append_step_summary,
    read_metadata,
    read_metadata_raw,
    write_metadata_raw,
    write_text,
    ensure_dir,
)
from scripts.release.build_plugin import EXCLUDE_PATTERNS, _copy_plugin_files
from scripts.release.create_release import create_github_release, prune_old_releases

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("release_cbms")

METADATA_PATH = "metadata.txt"
PUBLIC_DIR = "docs/user-guide/public"
CBMS_XML_PATH = f"{PUBLIC_DIR}/gemma-cbms.xml"
CBMS_JSON_PATH = f"{PUBLIC_DIR}/latest-cbms.json"
ROOT_FOLDER_NAME = "gemma-cbmsbeta"


def xml_escape(text: str) -> str:
    """Escape special XML characters in text content."""
    return xml_escape_impl(text, entities={"'": "&apos;", '"': "&quot;"})


def patch_cbms_staged_plugin(
    plugin_dir: Path,
    preview_version: str,
    revision: str,
    branch: str,
) -> None:
    """Patch plugin files in the staged directory for side-by-side coexistence."""
    logger.info("Applying side-by-side patches to staged directory (%s)...", plugin_dir.name)

    # ── 1. Patch metadata.txt ───────────────────────────────────────────────
    metadata_file = plugin_dir / "metadata.txt"
    if metadata_file.exists():
        content = read_metadata_raw(metadata_file)

        # Get latest commit message for changelog
        commit_msg = "Automated CBMS preview release"
        try:
            res = subprocess.run(
                ["git", "log", "-1", "--pretty=format:%s"],
                capture_output=True,
                text=True,
                check=True,
            )
            commit_msg = res.stdout.strip() or commit_msg
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        content = re.sub(r"^name=.*$", "name=GEMMA (CBMS Beta)", content, flags=re.MULTILINE)
        content = re.sub(r"^version=.*$", f"version={preview_version}", content, flags=re.MULTILINE)
        content = re.sub(r"^experimental=.*$", "experimental=True", content, flags=re.MULTILINE)

        # Prepend preview changelog entry
        preview_entry = f"{preview_version}: CBMS Preview build {revision} [{branch}] - {commit_msg}"
        content = re.sub(r"^changelog=", f"changelog={preview_entry}\n    ", content, flags=re.MULTILINE)

        write_metadata_raw(metadata_file, content)
        logger.info("  ✓ metadata.txt patched: name='GEMMA (CBMS Beta)', version=%s", preview_version)

    # ── 2. Patch gmd_pipeline_provider.py ──────────────────────────────────
    provider_file = plugin_dir / "gmd_pipeline_provider.py"
    if provider_file.exists():
        p_content = provider_file.read_text(encoding="utf-8")
        p_content = re.sub(
            r"def id\(self\):\s+return ['\"]gmd_pipeline['\"]",
            "def id(self):\n        return 'gmd_cbms_pipeline'",
            p_content,
        )
        p_content = re.sub(
            r"def name\(self\):\s+return ['\"]GMD Pipeline['\"]",
            "def name(self):\n        return 'GMD CBMS Pipeline'",
            p_content,
        )
        provider_file.write_text(p_content, encoding="utf-8")
        logger.info("  ✓ gmd_pipeline_provider.py patched: id='gmd_cbms_pipeline', name='GMD CBMS Pipeline'")

    # ── 3. Patch gmd_pipeline.py ───────────────────────────────────────────
    main_py_file = plugin_dir / "gmd_pipeline.py"
    if main_py_file.exists():
        m_content = main_py_file.read_text(encoding="utf-8")
        # Menu title
        m_content = m_content.replace('QMenu("Gemma")', 'QMenu("Gemma (CBMS)")')
        m_content = m_content.replace('addPluginToMenu("&Gemma",', 'addPluginToMenu("&Gemma (CBMS)",')
        # Toolbar name
        m_content = m_content.replace('addToolBar("Gemma Toolbar")', 'addToolBar("Gemma CBMS Toolbar")')
        m_content = m_content.replace('setObjectName("Gemma Toolbar")', 'setObjectName("Gemma CBMS Toolbar")')
        main_py_file.write_text(m_content, encoding="utf-8")
        logger.info("  ✓ gmd_pipeline.py patched: menu='Gemma (CBMS)', toolbar='Gemma CBMS Toolbar'")

    # ── 4. Patch cbmsmv_dialog.py (processing provider alignment) ──────────
    cbmsmv_file = plugin_dir / "references" / "cbms_mv" / "cbmsmv_dialog.py"
    if cbmsmv_file.exists():
        c_content = cbmsmv_file.read_text(encoding="utf-8")
        c_content = c_content.replace('"gmd_pipeline:', '"gmd_cbms_pipeline:')
        c_content = c_content.replace("'gmd_pipeline:", "'gmd_cbms_pipeline:")
        cbmsmv_file.write_text(c_content, encoding="utf-8")
        logger.info("  ✓ cbmsmv_dialog.py patched: algorithm prefix updated to 'gmd_cbms_pipeline:'")

    # ── 5. Patch create_enumeration_area dialog.py ─────────────────────────
    ea_dialog_file = plugin_dir / "references" / "create_enumeration_area" / "dialog.py"
    if ea_dialog_file.exists():
        e_content = ea_dialog_file.read_text(encoding="utf-8")
        e_content = e_content.replace('ALGORITHM_ID = "gmd_pipeline:createea"', 'ALGORITHM_ID = "gmd_cbms_pipeline:createea"')
        ea_dialog_file.write_text(e_content, encoding="utf-8")
        logger.info("  ✓ create_enumeration_area/dialog.py patched: ALGORITHM_ID='gmd_cbms_pipeline:createea'")


def create_cbms_zip(staging_dir: str, output_path: Path, root_folder: str = ROOT_FOLDER_NAME) -> None:
    """Create a ZIP file containing root_folder from staging_dir."""
    try:
        subprocess.run(
            ["zip", "-r", str(output_path), f"{root_folder}/"],
            cwd=staging_dir,
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        logger.info("System 'zip' not found — using Python shutil.make_archive")
        shutil.make_archive(
            str(output_path).replace(".zip", ""),
            "zip",
            root_dir=staging_dir,
            base_dir=root_folder,
        )


def build_cbms_plugin_zip(
    preview_version: str,
    revision: str,
    branch: str,
    output_name: str,
    source_dir: str = ".",
) -> Path:
    """Stage and build the CBMS QGIS plugin ZIP with root folder gemma-cbmsbeta/."""
    source = Path(source_dir).resolve()
    output_path = source / output_name

    if output_path.exists():
        output_path.unlink()

    with tempfile.TemporaryDirectory(prefix="gemma_cbms_") as tmp_dir:
        staged_plugin_dir = Path(tmp_dir) / ROOT_FOLDER_NAME
        staged_plugin_dir.mkdir(parents=True)

        logger.info("Staging CBMS plugin files to %s...", staged_plugin_dir)
        _copy_plugin_files(source, staged_plugin_dir)

        # Apply side-by-side patches
        patch_cbms_staged_plugin(
            staged_plugin_dir,
            preview_version=preview_version,
            revision=revision,
            branch=branch,
        )

        logger.info("Creating ZIP: %s", output_name)
        create_cbms_zip(tmp_dir, output_path, root_folder=ROOT_FOLDER_NAME)

    logger.info("✅ CBMS Plugin ZIP created: %s", output_path.name)
    return output_path


def build_cbms_xml(
    metadata: dict[str, str],
    preview_version: str,
    download_url: str,
    date_str: str,
    source_owner: str,
    source_repo: str,
    branch: str,
) -> str:
    """Build QGIS repository XML for the CBMS beta channel."""
    description = metadata.get("description", "GIS Extension for Map Management and Analysis")
    about = metadata.get("about", "")
    tags = metadata.get("tags", "")

    cbms_description = f"{description} (CBMS Beta Channel)"
    cbms_about = f"{about} (CBMS Beta Channel)"
    cbms_tags = f"{tags},cbms,beta" if tags else "cbms,beta"
    icon_url = f"https://raw.githubusercontent.com/{source_owner}/{source_repo}/{branch}/icons/icon.png"

    xml_template = """\
<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet type="text/xsl" href=""?>
<plugins>
  <pyqgis_plugin name="{name}" version="{version}">
    <version>{version}</version>
    <description>{description}</description>
    <about>{about}</about>
    <author>{author}</author>
    <author_name>{author}</author_name>
    <qgis_minimum_version>{qgis_minimum_version}</qgis_minimum_version>
    <homepage>{homepage}</homepage>
    <download_url>{download_url}</download_url>
    <icon>{icon}</icon>
    <file_name>gemma-cbmsbeta.zip</file_name>
    <upload_date>{date}</upload_date>
    <update_date>{date}</update_date>
    <experimental>True</experimental>
    <deprecated>False</deprecated>
    <tracker>{tracker}</tracker>
    <repository>{repository}</repository>
    <tags>{tags}</tags>
    <category>{category}</category>
    <server>{server}</server>
  </pyqgis_plugin>
</plugins>"""

    return xml_template.format(
        name=xml_escape("GEMMA (CBMS Beta)"),
        version=xml_escape(preview_version),
        description=xml_escape(cbms_description),
        about=xml_escape(cbms_about),
        author=xml_escape(metadata.get("author", "Geospatial Management Division")),
        qgis_minimum_version=xml_escape(metadata.get("qgisMinimumVersion", "3.0")),
        homepage=f"https://github.com/{source_owner}/{source_repo}/tree/{branch}",
        download_url=download_url,
        icon=icon_url,
        date=date_str,
        tracker=f"https://github.com/{source_owner}/{source_repo}/issues",
        repository=f"https://github.com/{source_owner}/{source_repo}",
        tags=xml_escape(cbms_tags),
        category=xml_escape(metadata.get("category", "Processing Provider")),
        server=metadata.get("server", "False"),
    )


def run_cbms_pipeline(args: argparse.Namespace) -> None:
    """Execute the CBMS preview release pipeline."""
    github_token = os.environ.get("GITHUB_TOKEN", "")
    repo_full = os.environ.get("GITHUB_REPOSITORY", "GMD-Repository/gemma-plugin")
    source_owner, source_repo = repo_full.split("/")
    preview_owner = args.preview_owner
    preview_repo = args.preview_repo
    branch = args.branch
    today = date.today().isoformat()

    # ── Step 1: Calculate revision ────────────────────────────────────────
    logger.info("═══ Step 1: Calculate revision ═══")
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        rev_num = result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("Could not calculate revision from git — using fallback")
        rev_num = "0"

    revision = f"r{rev_num}"
    tag_name = f"cbms-{revision}"
    logger.info("Revision: %s | Release Tag: %s", revision, tag_name)

    # Read base version from metadata.txt
    metadata = read_metadata(METADATA_PATH)
    base_version = metadata.get("version", "0.0.0").strip()
    preview_version = f"{base_version}-cbms-{revision}"

    set_github_output("revision", revision)
    set_github_output("preview_version", preview_version)
    set_github_output("tag_name", tag_name)

    # ── Step 2: Build plugin ZIP ──────────────────────────────────────────
    logger.info("═══ Step 2: Build CBMS plugin ZIP (root: %s/) ═══", ROOT_FOLDER_NAME)
    zip_name = f"gemma-cbmsbeta-{revision}.zip"
    zip_path = build_cbms_plugin_zip(
        preview_version=preview_version,
        revision=revision,
        branch=branch,
        output_name=zip_name,
    )
    set_github_output("zip_name", zip_name)

    download_url = f"https://github.com/{preview_owner}/{preview_repo}/releases/download/{tag_name}/{zip_name}"
    set_github_output("download_url", download_url)

    # ── Step 3: Create GitHub Release ─────────────────────────────────────
    logger.info("═══ Step 3: Create GitHub Release on %s/%s ═══", preview_owner, preview_repo)
    if args.dry_run:
        logger.info("[DRY RUN] Skipping GitHub Release creation and pruning")
        release_url = f"https://github.com/{preview_owner}/{preview_repo}/releases/tag/{tag_name}"
    else:
        create_github_release(
            owner=preview_owner,
            repo=preview_repo,
            tag=tag_name,
            version=preview_version,
            highlights=[],
            zip_path=zip_path,
            token=github_token,
            prerelease=False,
            release_name=f"GEMMA CBMS Preview {revision}",
        )
        logger.info("═══ Step 3b: Prune old CBMS releases (prefix: 'cbms-') ═══")
        prune_old_releases(
            owner=preview_owner,
            repo=preview_repo,
            token=github_token,
            keep_count=args.max_previews,
            tag_prefix="cbms-",
        )
        release_url = f"https://github.com/{preview_owner}/{preview_repo}/releases/tag/{tag_name}"

    set_github_output("release_url", release_url)

    # ── Step 4: Update gemma-cbms.xml ─────────────────────────────────────
    logger.info("═══ Step 4: Update %s ═══", CBMS_XML_PATH)
    xml_content = build_cbms_xml(
        metadata=metadata,
        preview_version=preview_version,
        download_url=download_url,
        date_str=today,
        source_owner=source_owner,
        source_repo=source_repo,
        branch=branch,
    )
    ensure_dir(PUBLIC_DIR)
    write_text(CBMS_XML_PATH, xml_content)
    logger.info("✅ %s generated", CBMS_XML_PATH)

    # ── Step 5: Update latest-cbms.json ───────────────────────────────────
    logger.info("═══ Step 5: Update %s ═══", CBMS_JSON_PATH)
    raw_repo_url = f"https://raw.githubusercontent.com/{source_owner}/{source_repo}/{branch}/{CBMS_XML_PATH}"
    latest_data = {
        "version": preview_version,
        "revision": revision,
        "tag": tag_name,
        "releaseDate": today,
        "repositoryUrl": raw_repo_url,
        "downloadUrl": download_url,
        "releaseUrl": release_url,
        "branch": branch,
    }
    write_text(CBMS_JSON_PATH, json.dumps(latest_data, indent=2) + "\n")
    logger.info("✅ %s generated", CBMS_JSON_PATH)
    set_github_output("repository_url", raw_repo_url)

    # ── Step 6: Step summary ──────────────────────────────────────────────
    summary = "\n".join([
        "# GEMMA Plugin — CBMS Closed Beta Release",
        "",
        f"> **Version:** `{preview_version}`  ·  **Tag:** `{tag_name}`  ·  **Branch:** `{branch}`",
        "",
        "---",
        "",
        "### QGIS Repository Setup for Closed Beta Testers",
        "",
        "In QGIS, go to **Plugins → Manage and Install Plugins → Settings → Plugin Repositories → Add...**",
        "",
        f"- **Name:** `GEMMA CBMS Beta`",
        f"- **URL:** `{raw_repo_url}`",
        "",
        "> Ensure **\"Show also experimental plugins\"** is checked under Settings.",
        "",
        "---",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Version | `{preview_version}` |",
        f"| Tag | `{tag_name}` |",
        f"| Branch | `{branch}` |",
        f"| Zip Root Folder | `{ROOT_FOLDER_NAME}/` |",
        f"| Download Asset | [Download ZIP]({download_url}) |",
        f"| Release Page | [View Release]({release_url}) |",
    ])
    append_step_summary(summary)
    logger.info("✅ CBMS preview pipeline completed: %s (%s)", tag_name, preview_version)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="GEMMA Plugin CBMS Closed Beta Release Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--branch",
        default="cbms_main",
        help="Target branch for the CBMS release (default: cbms_main).",
    )
    parser.add_argument(
        "--preview-owner",
        default="GMD-Repository",
        help="GitHub owner for the preview release repo (default: GMD-Repository).",
    )
    parser.add_argument(
        "--preview-repo",
        default=os.environ.get("CBMS_PREVIEW_REPO", "gemma-plugin-closed-preview"),
        help="GitHub repository for preview release assets (default: gemma-plugin-closed-preview).",
    )
    parser.add_argument(
        "--max-previews",
        type=int,
        default=10,
        help="Maximum old CBMS preview releases to retain (default: 10).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run without mutating GitHub Releases.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_cbms_pipeline(args)
