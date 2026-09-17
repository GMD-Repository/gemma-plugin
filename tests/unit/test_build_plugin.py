"""
Unit tests for QGIS plugin ZIP packaging and exclusion rules.
"""

import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.release.build_plugin import (
    EXCLUDE_PATTERNS,
    _copy_plugin_files,
    _should_exclude,
    build_plugin_zip,
)


class TestBuildPluginZipExclusions(unittest.TestCase):
    """Test suite ensuring test directories and dev files are excluded from plugin ZIPs."""

    def test_test_folders_in_exclude_patterns(self):
        """Ensure test-related patterns are registered in EXCLUDE_PATTERNS."""
        self.assertIn("tests", EXCLUDE_PATTERNS)
        self.assertIn("tests/*", EXCLUDE_PATTERNS)
        self.assertIn("test", EXCLUDE_PATTERNS)
        self.assertIn("test/*", EXCLUDE_PATTERNS)
        self.assertIn(".pytest_cache", EXCLUDE_PATTERNS)

    def test_should_exclude_test_directories(self):
        """Verify _should_exclude returns True for tests directory and nested test files."""
        root = Path("/fake/root")
        self.assertTrue(_should_exclude(root / "tests", root))
        self.assertTrue(_should_exclude(root / "tests" / "unit" / "test_foo.py", root))
        self.assertTrue(_should_exclude(root / "test", root))
        self.assertTrue(_should_exclude(root / "test" / "test_bar.py", root))
        self.assertTrue(_should_exclude(root / ".pytest_cache", root))
        self.assertTrue(_should_exclude(root / "scratch", root))
        self.assertTrue(_should_exclude(root / ".claude", root))

    def test_should_not_exclude_plugin_essentials(self):
        """Verify _should_exclude returns False for core plugin files."""
        root = Path("/fake/root")
        self.assertFalse(_should_exclude(root / "metadata.txt", root))
        self.assertFalse(_should_exclude(root / "__init__.py", root))
        self.assertFalse(_should_exclude(root / "gmd_pipeline.py", root))
        self.assertFalse(_should_exclude(root / "gmd_pipeline_provider.py", root))
        self.assertFalse(_should_exclude(root / "gmd_scripts", root))
        self.assertFalse(_should_exclude(root / "icons", root))
        self.assertFalse(_should_exclude(root / "references", root))

    def test_build_plugin_zip_omits_tests_directory(self):
        """Verify build_plugin_zip does not package tests folder into ZIP archive."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            src_dir = Path(tmp_dir) / "fake_plugin"
            src_dir.mkdir()

            # Create standard plugin files
            (src_dir / "metadata.txt").write_text("name=GEMMA\nversion=1.0.0\n", encoding="utf-8")
            (src_dir / "__init__.py").write_text("# init", encoding="utf-8")
            (src_dir / "gmd_pipeline.py").write_text("# pipeline", encoding="utf-8")

            # Create test folder with test files
            tests_dir = src_dir / "tests"
            tests_dir.mkdir()
            (tests_dir / "__init__.py").write_text("# test init", encoding="utf-8")
            (tests_dir / "test_example.py").write_text("# test code", encoding="utf-8")

            # Create docs & scripts folders
            docs_dir = src_dir / "docs"
            docs_dir.mkdir()
            (docs_dir / "index.md").write_text("# docs", encoding="utf-8")

            # 1. Test Stable build
            stable_zip_name = "test-stable.zip"
            zip_path = build_plugin_zip(
                version="1.0.0",
                output_name=stable_zip_name,
                source_dir=str(src_dir),
                is_preview=False,
            )

            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    namelist = zf.namelist()
                    # Ensure plugin root directory exists
                    self.assertTrue(any(name.startswith("gemma-plugin/") for name in namelist))
                    self.assertIn("gemma-plugin/metadata.txt", namelist)
                    self.assertIn("gemma-plugin/__init__.py", namelist)

                    # Ensure tests and docs are NOT present
                    test_files = [name for name in namelist if "test" in name.lower()]
                    self.assertEqual(
                        test_files,
                        [],
                        f"Found test files in stable ZIP: {test_files}",
                    )
                    self.assertFalse(any(name.startswith("gemma-plugin/docs") for name in namelist))
            finally:
                if zip_path.exists():
                    zip_path.unlink()

            # 2. Test Preview build
            preview_zip_name = "test-preview.zip"
            preview_zip_path = build_plugin_zip(
                version="1.0.0-r999",
                output_name=preview_zip_name,
                source_dir=str(src_dir),
                is_preview=True,
                preview_revision="r999",
                preview_branch="dev",
            )

            try:
                with zipfile.ZipFile(preview_zip_path, "r") as zf:
                    namelist = zf.namelist()
                    self.assertIn("gemma-plugin/metadata.txt", namelist)

                    # Ensure tests are NOT present in preview ZIP either
                    test_files = [name for name in namelist if "test" in name.lower()]
                    self.assertEqual(
                        test_files,
                        [],
                        f"Found test files in preview ZIP: {test_files}",
                    )
            finally:
                if preview_zip_path.exists():
                    preview_zip_path.unlink()


if __name__ == "__main__":
    unittest.main()
