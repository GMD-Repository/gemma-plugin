#!/usr/bin/env python3
"""
GEMMA Plugin — Release Pipeline Orchestrator

Main entry point for both stable and preview release workflows.
Called from GitHub Actions with minimal YAML orchestration.

Usage:
    # Stable release
    python scripts/release/release_pipeline.py \
        --mode stable \
        --bump-type auto \
        --custom-version ""

    # Preview release
    python scripts/release/release_pipeline.py \
        --mode preview \
        --branch main

    # Dry-run (no GitHub API mutations)
    python scripts/release/release_pipeline.py \
        --mode stable \
        --bump-type minor \
        --dry-run

Environment variables:
    GITHUB_TOKEN        GitHub API token (required)
    AI_TOKEN            Token with models:read permission (stable only)
    GITHUB_REPOSITORY   Owner/repo (e.g. "GMD-Repository/gemma-plugin")
    GITHUB_OUTPUT       Path to output file (set by GitHub Actions)
    GITHUB_STEP_SUMMARY Path to step summary file (set by GitHub Actions)
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

# Ensure the repo root is on the Python path so scripts.* imports work
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.utils.files import set_github_output, append_step_summary
from scripts.utils.github import tag_exists
from scripts.release.update_metadata import resolve_version, update_metadata_changelog
from scripts.release.collect_changes import collect_changes
from scripts.release.generate_changelog import generate_changelog
from scripts.release.update_docs import (
    update_changelogs,
    update_latest_json,
    update_latest_beta_json,
    update_releases_json,
)
from scripts.release.update_repository_xml import update_stable_xml, update_beta_xml
from scripts.release.update_vitepress_config import update_vitepress_version
from scripts.release.build_plugin import build_plugin_zip
from scripts.release.create_release import create_github_release, prune_old_releases

logger = logging.getLogger(__name__)

METADATA_PATH = "metadata.txt"


# ── Stable Release Pipeline ──────────────────────────────────────────────────


def commit_and_push_stable_release(
    version: str,
    token: str,
    repo_full: str,
    dry_run: bool = False,
) -> None:
    """Commit updated release metadata and documentation directly to main."""
    if dry_run:
        logger.info("[DRY RUN] Skipping git commit and push for stable release")
        return

    logger.info("═══ Commit & Push release metadata directly to main ═══")
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)

        files_to_commit = [
            "metadata.txt",
            "CHANGELOG.md",
            "docs/user-guide/changelog.md",
            "docs/user-guide/public/gemma.xml",
            "docs/user-guide/public/latest.json",
            "docs/user-guide/public/releases.json",
            "docs/.vitepress/config.mts",
        ]

        for file_path in files_to_commit:
            if Path(file_path).exists():
                subprocess.run(["git", "add", file_path], check=True)

        diff_check = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if diff_check.returncode != 0:
            commit_msg = f"chore(release): update metadata and release data for v{version} [skip ci]"
            subprocess.run(["git", "commit", "-m", commit_msg], check=True)
            if token:
                remote_url = f"https://x-access-token:{token}@github.com/{repo_full}.git"
                subprocess.run(["git", "push", remote_url, "HEAD:main"], check=True)
            else:
                subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)
            logger.info("✅ Direct release commit pushed to main for v%s", version)
        else:
            logger.info("No modified release metadata files to commit.")
    except subprocess.CalledProcessError as err:
        logger.error("Failed to commit/push release metadata: %s", err)
        raise


def run_stable_pipeline(args: argparse.Namespace) -> None:
    """Execute the full stable release pipeline.

    Steps:
    1. Resolve version from metadata.txt
    2. Check if tag already exists
    3. Collect changes from GitHub
    4. Generate AI changelog
    5. Update metadata.txt changelog
    6. Update CHANGELOG.md + docs changelog + release JSON files
    7. Update gemma.xml
    8. Update VitePress navbar version
    9. Build plugin ZIP
    10. Create GitHub Release + upload asset
    11. Write job summary
    """
    github_token = os.environ.get("GITHUB_TOKEN", "")
    ai_token = os.environ.get("AI_TOKEN", github_token)
    repo_full = os.environ.get("GITHUB_REPOSITORY", "GMD-Repository/gemma-plugin")
    owner, repo = repo_full.split("/")
    today = date.today().isoformat()

    # ── Step 1: Resolve version ───────────────────────────────────────────
    logger.info("═══ Step 1: Resolve version ═══")
    version, tag = resolve_version(
        METADATA_PATH,
        bump_type=args.bump_type,
        custom_version=args.custom_version,
    )
    set_github_output("version", version)
    set_github_output("tag", tag)
    logger.info("Version: %s | Tag: %s", version, tag)

    # ── Step 2: Check for existing tag ────────────────────────────────────
    logger.info("═══ Step 2: Check existing tag ═══")
    if tag_exists(tag):
        logger.info("Tag %s already exists — skipping release.", tag)
        set_github_output("released", "false")
        return

    set_github_output("released", "true")

    # ── Step 3: Collect changes ───────────────────────────────────────────
    logger.info("═══ Step 3: Collect changes ═══")
    if args.dry_run:
        logger.info("[DRY RUN] Skipping change collection")
        raw_lines = ["Sample change for dry run testing"]
        previous_tag = None
        pr_count = 0
        commit_count = 0
    else:
        changes_result = collect_changes(owner, repo, tag, github_token)
        raw_lines = changes_result.raw_lines
        previous_tag = changes_result.previous_tag
        pr_count = changes_result.pr_count
        commit_count = changes_result.commit_count

    # ── Step 4: Generate AI changelog ─────────────────────────────────────
    logger.info("═══ Step 4: Generate AI changelog ═══")
    if args.dry_run:
        logger.info("[DRY RUN] Skipping AI changelog generation")
        from scripts.release.generate_changelog import ChangelogResult
        changelog = ChangelogResult(
            summary="Dry run release.",
            changes={"features": raw_lines, "improvements": [], "fixes": []},
            highlights=raw_lines,
            ai_generated=False,
        )
    else:
        changelog = generate_changelog(
            version=version,
            raw_lines=raw_lines,
            ai_token=ai_token,
        )

    logger.info("Changelog: %d highlights (AI=%s)", len(changelog.highlights), changelog.ai_generated)

    # ── Step 5: Update metadata.txt ───────────────────────────────────────
    logger.info("═══ Step 5: Update metadata.txt ═══")
    update_metadata_changelog(METADATA_PATH, version, changelog.highlights)

    # ── Step 6: Update docs + release JSON ────────────────────────────────
    logger.info("═══ Step 6: Update docs and release JSON ═══")
    update_changelogs(version, today, changelog.changes)
    update_latest_json(version, tag, today, owner, repo)
    update_releases_json(version, tag, today, changelog.changes, owner=owner, repo=repo)

    # ── Step 7: Update gemma.xml ──────────────────────────────────────────
    logger.info("═══ Step 7: Update gemma.xml ═══")
    update_stable_xml(METADATA_PATH, version, tag, owner, repo)

    # ── Step 8: Update VitePress navbar version ───────────────────────────
    logger.info("═══ Step 8: Update VitePress navbar version ═══")
    try:
        update_vitepress_version(version)
    except Exception as err:
        logger.warning("Failed to update VitePress config: %s", err)
        if not args.dry_run:
            raise

    # ── Step 8b: Commit & Push release metadata directly to main ─────────
    commit_and_push_stable_release(version, github_token, repo_full, dry_run=args.dry_run)

    # ── Step 9: Build plugin ZIP ──────────────────────────────────────────
    logger.info("═══ Step 9: Build plugin ZIP ═══")
    zip_name = f"gemma-plugin-v{version}.zip"
    zip_path = build_plugin_zip(version=version, output_name=zip_name)
    set_github_output("zip_name", zip_name)

    # ── Step 10: Create GitHub Release ─────────────────────────────────────
    logger.info("═══ Step 10: Create GitHub Release ═══")
    if args.dry_run:
        logger.info("[DRY RUN] Skipping GitHub Release creation")
        release_url = "https://github.com/dry-run"
    else:
        release_result = create_github_release(
            owner=owner,
            repo=repo,
            tag=tag,
            version=version,
            highlights=changelog.highlights,
            zip_path=zip_path,
            token=github_token,
        )
        release_url = release_result.html_url
        set_github_output("release_url", release_url)

    # Export release body for email notification step
    bullet_list = "\n".join(f"- {h}" for h in changelog.highlights)
    set_github_output("release_body", bullet_list)

    # ── Step 11: Job summary ──────────────────────────────────────────────
    logger.info("═══ Step 11: Write job summary ═══")
    date_display = datetime.now().strftime("%B %d, %Y")
    summary = "\n".join([
        "# GEMMA Plugin — Stable Release",
        "",
        f"> **Version:** `v{version}`  ·  **Date:** {date_display}  ·  "
        f"**AI Generated:** {'✅ Yes' if changelog.ai_generated else '⚠️ Fallback'}",
        "",
        "---",
        "",
        "## What's New",
        "",
        bullet_list,
        "",
        "---",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Tag | `{tag}` |",
        f"| Previous Tag | `{previous_tag or 'none (first release)'}` |",
        f"| PR Lines | {pr_count} |",
        f"| Commit Lines | {commit_count} |",
        f"| ZIP File | `{zip_name}` |",
        f"| Release | [View on GitHub]({release_url}) |",
    ])
    append_step_summary(summary)

    logger.info("✅ Stable release pipeline completed for v%s", version)


# ── Preview Release Pipeline ─────────────────────────────────────────────────


def run_preview_pipeline(args: argparse.Namespace) -> None:
    """Execute the preview/beta release pipeline.

    Steps:
    1. Calculate revision number from git
    2. Build plugin ZIP with preview metadata
    3. Create pre-release on gemma-plugin-preview repo
    4. Update gemma-beta.xml
    5. Update latest-beta.json
    """
    github_token = os.environ.get("GITHUB_TOKEN", "")
    repo_full = os.environ.get("GITHUB_REPOSITORY", "GMD-Repository/gemma-plugin")
    source_owner, source_repo = repo_full.split("/")
    preview_owner = "GMD-Repository"
    preview_repo = "gemma-plugin-preview"
    today = date.today().isoformat()
    branch = args.branch

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
    logger.info("Revision: %s", revision)

    # Read base version from metadata.txt
    from scripts.utils.files import read_metadata
    metadata = read_metadata(METADATA_PATH)
    base_version = metadata.get("version", "0.0.0").strip()
    preview_version = f"{base_version}-{revision}"

    set_github_output("revision", revision)
    set_github_output("preview_version", preview_version)

    # ── Step 2: Build plugin ZIP ──────────────────────────────────────────
    logger.info("═══ Step 2: Build plugin ZIP ═══")
    zip_name = f"gemma-plugin-{revision}.zip"
    zip_path = build_plugin_zip(
        version=preview_version,
        output_name=zip_name,
        is_preview=True,
        preview_revision=revision,
        preview_branch=branch,
    )
    set_github_output("zip_name", zip_name)

    # ── Step 3: Create pre-release ────────────────────────────────────────
    logger.info("═══ Step 3: Create preview release ═══")
    if args.dry_run:
        logger.info("[DRY RUN] Skipping preview release creation")
    else:
        create_github_release(
            owner=preview_owner,
            repo=preview_repo,
            tag=revision,
            version=preview_version,
            highlights=[],
            zip_path=zip_path,
            token=github_token,
            prerelease=False,  # Preview repo treats these as latest
            release_name=f"GEMMA Preview {revision}",
        )
        logger.info("═══ Step 3b: Prune old preview releases ═══")
        prune_old_releases(
            owner=preview_owner,
            repo=preview_repo,
            token=github_token,
            keep_count=args.max_previews,
        )

    # ── Step 4: Update gemma-beta.xml ─────────────────────────────────────
    logger.info("═══ Step 4: Update gemma-beta.xml ═══")
    update_beta_xml(
        metadata_path=METADATA_PATH,
        preview_version=preview_version,
        revision=revision,
        zip_name=zip_name,
        preview_owner=preview_owner,
        preview_repo=preview_repo,
        source_owner=source_owner,
        source_repo=source_repo,
    )

    # ── Step 5: Update latest-beta.json ───────────────────────────────────
    logger.info("═══ Step 5: Update latest-beta.json ═══")
    update_latest_beta_json(
        preview_version=preview_version,
        revision=revision,
        date=today,
        preview_owner=preview_owner,
        preview_repo=preview_repo,
    )

    logger.info("✅ Preview release pipeline completed: %s (%s)", revision, preview_version)


# ── CLI entry point ────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="GEMMA Plugin Release Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--mode",
        required=True,
        choices=["stable", "preview"],
        help="Release mode: 'stable' for tagged releases, 'preview' for CI preview builds.",
    )
    parser.add_argument(
        "--bump-type",
        default="auto",
        choices=["auto", "patch", "minor", "major"],
        help="SemVer bump type (stable mode only). Default: auto.",
    )
    parser.add_argument(
        "--custom-version",
        default="",
        help="Custom version override (stable mode only). E.g. '3.1.0'.",
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="Branch name (preview mode only). Default: main.",
    )
    parser.add_argument(
        "--max-previews",
        type=int,
        default=10,
        help="Maximum number of preview releases to retain (preview mode only). Default: 10.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without making GitHub API calls (no releases, no asset uploads).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )

    return parser.parse_args()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the release pipeline."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def main() -> None:
    """Main entry point."""
    args = parse_args()
    setup_logging(verbose=args.verbose)

    logger.info("╔══════════════════════════════════════════════════╗")
    logger.info("║  GEMMA Plugin — Release Pipeline                ║")
    logger.info("║  Mode: %-41s ║", args.mode.upper())
    if args.dry_run:
        logger.info("║  ⚠️  DRY RUN — no GitHub API mutations           ║")
    logger.info("╚══════════════════════════════════════════════════╝")

    try:
        if args.mode == "stable":
            run_stable_pipeline(args)
        elif args.mode == "preview":
            run_preview_pipeline(args)
    except Exception as e:
        logger.error("❌ Pipeline failed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
