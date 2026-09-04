"""
Unit tests for changelog author and PR tag extraction, cleaning, and deduplication.
"""

import unittest
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed
setup_qgis_mock_if_needed()

from scripts.release.collect_changes import _clean_line
from scripts.release.generate_changelog import (
    _parse_item_tags,
    _enrich_with_author_and_pr_tags,
)


class TestChangelogCleaning(unittest.TestCase):
    """Test suite for changelog line cleaning and tag deduplication."""

    def test_clean_line_embedded_author_and_pr(self):
        """Embedded (@user #123) should be stripped from text and formatted as canonical links."""
        raw = "Implemented EA merge processor, EARF Excel writer, and phase 8 output (@pacoleslaw #192)"
        cleaned = _clean_line(raw, owner="GMD-Repository", repo="gemma-plugin")
        expected = (
            "Implemented EA merge processor, EARF Excel writer, and phase 8 output "
            "([@pacoleslaw](https://github.com/pacoleslaw)) "
            "([#192](https://github.com/GMD-Repository/gemma-plugin/pull/192))"
        )
        self.assertEqual(cleaned, expected)

    def test_clean_line_strips_duplicate_tags(self):
        """Already duplicated line should be sanitized to single canonical tags."""
        raw = (
            "Implemented EA merge processor, EARF Excel writer, and phase 8 output "
            "(@pacoleslaw #192) ([@pacoleslaw](https://github.com/pacoleslaw)) "
            "([#192](https://github.com/GMD-Repository/gemma-plugin/pull/192))"
        )
        cleaned = _clean_line(raw, owner="GMD-Repository", repo="gemma-plugin")
        expected = (
            "Implemented EA merge processor, EARF Excel writer, and phase 8 output "
            "([@pacoleslaw](https://github.com/pacoleslaw)) "
            "([#192](https://github.com/GMD-Repository/gemma-plugin/pull/192))"
        )
        self.assertEqual(cleaned, expected)

    def test_clean_line_prioritizes_embedded_author_over_committer(self):
        """Embedded author (@kentemman-gmd) should be preferred over merge committer (pacoleslaw)."""
        raw = "Implemented EA output phase with geometric refinement (@kentemman-gmd #196)"
        cleaned = _clean_line(
            raw,
            author_login="pacoleslaw",
            owner="GMD-Repository",
            repo="gemma-plugin",
        )
        expected = (
            "Implemented EA output phase with geometric refinement "
            "([@kentemman-gmd](https://github.com/kentemman-gmd)) "
            "([#196](https://github.com/GMD-Repository/gemma-plugin/pull/196))"
        )
        self.assertEqual(cleaned, expected)

    def test_clean_line_release_notes_by_author(self):
        """Line from GitHub release notes 'by @user in https://...' is formatted properly."""
        raw = (
            "* feat(ea): Implemented EA delineation workflow by @pacoleslaw in "
            "https://github.com/GMD-Repository/gemma-plugin/pull/193"
        )
        cleaned = _clean_line(raw, owner="GMD-Repository", repo="gemma-plugin")
        expected = (
            "Implemented EA delineation workflow "
            "([@pacoleslaw](https://github.com/pacoleslaw)) "
            "([#193](https://github.com/GMD-Repository/gemma-plugin/pull/193))"
        )
        self.assertEqual(cleaned, expected)

    def test_clean_line_ignores_bot_accounts(self):
        """Automated bots should not be attached as author tags."""
        raw = "Update dependencies (#100)"
        cleaned = _clean_line(
            raw,
            author_login="github-actions[bot]",
            owner="GMD-Repository",
            repo="gemma-plugin",
        )
        expected = "Update dependencies ([#100](https://github.com/GMD-Repository/gemma-plugin/pull/100))"
        self.assertEqual(cleaned, expected)

    def test_parse_item_tags(self):
        """_parse_item_tags accurately separates clean description from author and PR metadata."""
        text = "Fixed CRS issue (@psacjperez #90) ([@psacjperez](https://github.com/psacjperez)) ([#90](https://github.com/GMD-Repository/gemma-plugin/pull/90))"
        clean_text, author, pr_num, pr_url = _parse_item_tags(text)
        self.assertEqual(clean_text, "Fixed CRS issue")
        self.assertEqual(author, "psacjperez")
        self.assertEqual(pr_num, "90")
        self.assertEqual(pr_url, "https://github.com/GMD-Repository/gemma-plugin/pull/90")

    def test_enrich_with_author_and_pr_tags_no_doubles(self):
        """_enrich_with_author_and_pr_tags must prevent doubles from AI output."""
        raw_lines = [
            "Implemented EA merge processor ([@pacoleslaw](https://github.com/pacoleslaw)) ([#192](https://github.com/GMD-Repository/gemma-plugin/pull/192))",
            "Fixed LGU boundary clipping ([@ftating19](https://github.com/ftating19)) ([#194](https://github.com/GMD-Repository/gemma-plugin/pull/194))",
            "Optimized geometry repair ([@psacjperez](https://github.com/psacjperez)) ([#189](https://github.com/GMD-Repository/gemma-plugin/pull/189))",
        ]
        ai_changes = {
            "features": [
                "Implemented EA merge processor (@pacoleslaw #192) (@pacoleslaw) (#192)",
                "Implemented EA merge processor (@pacoleslaw #192) ([@pacoleslaw](https://github.com/pacoleslaw)) ([#192](https://github.com/GMD-Repository/gemma-plugin/pull/192))",
            ],
            "fixes": [
                "Fixed LGU boundary clipping (@ftating19 #194)",
            ],
            "improvements": [
                "Optimized geometry repair",  # No tags in AI output, should be enriched from matched raw line
            ],
        }
        enriched = _enrich_with_author_and_pr_tags(ai_changes, raw_lines)

        self.assertEqual(
            enriched["features"][0],
            "Implemented EA merge processor "
            "([@pacoleslaw](https://github.com/pacoleslaw)) "
            "([#192](https://github.com/GMD-Repository/gemma-plugin/pull/192))",
        )
        self.assertEqual(
            enriched["features"][1],
            "Implemented EA merge processor "
            "([@pacoleslaw](https://github.com/pacoleslaw)) "
            "([#192](https://github.com/GMD-Repository/gemma-plugin/pull/192))",
        )
        self.assertEqual(
            enriched["fixes"][0],
            "Fixed LGU boundary clipping "
            "([@ftating19](https://github.com/ftating19)) "
            "([#194](https://github.com/GMD-Repository/gemma-plugin/pull/194))",
        )
        self.assertEqual(
            enriched["improvements"][0],
            "Optimized geometry repair "
            "([@psacjperez](https://github.com/psacjperez)) "
            "([#189](https://github.com/GMD-Repository/gemma-plugin/pull/189))",
        )


if __name__ == "__main__":
    unittest.main()
