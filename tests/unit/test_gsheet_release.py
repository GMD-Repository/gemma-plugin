# -*- coding: utf-8 -*-
"""
Unit tests for gsheet_release.py (scripts/release/gsheet_release.py).
Tests email fetching from Google Sheet mock, deduplication, filtering,
and output saving.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from scripts.release.gsheet_release import fetch_emails, log_release


class TestGsheetRelease(unittest.TestCase):
    """Test suite for gsheet_release module."""

    def test_fetch_emails_from_mock_worksheet(self):
        """Test fetching and parsing emails from worksheet Column A."""
        mock_client = MagicMock()
        mock_sheet = MagicMock()
        mock_worksheet = MagicMock()

        mock_client.open_by_key.return_value = mock_sheet
        mock_sheet.worksheet.return_value = mock_worksheet

        # Header in row 1, 150 rows of data below it
        col_a_data = ["Header Email"] + [
            f"user_{i}@psa.gov.ph" for i in range(1, 151)
        ] + ["invalid-email", "", "user_1@psa.gov.ph"]  # Has duplicate and empty

        mock_worksheet.col_values.return_value = col_a_data

        emails = fetch_emails(mock_client, "test_spreadsheet_id", "email_gemma")

        # 150 unique valid emails
        self.assertEqual(len(emails), 150)
        self.assertEqual(emails[0], "user_1@psa.gov.ph")
        self.assertEqual(emails[149], "user_150@psa.gov.ph")
        self.assertNotIn("invalid-email", emails)
        self.assertNotIn("Header Email", emails)

    def test_log_release(self):
        """Test logging release details into worksheet."""
        mock_client = MagicMock()
        mock_sheet = MagicMock()
        mock_worksheet = MagicMock()

        mock_client.open_by_key.return_value = mock_sheet
        mock_sheet.worksheet.return_value = mock_worksheet
        mock_worksheet.get_all_values.return_value = [["Header1", "Header2"]]

        log_release(
            client=mock_client,
            spreadsheet_id="test_id",
            version="3.1.0",
            zip_name="gemma-plugin-3.1.0.zip",
            actor="test-actor",
            repo="GMD-Repository/gemma-plugin",
            worksheet_name="Releases",
        )

        mock_worksheet.append_row.assert_called_once()
        row_args = mock_worksheet.append_row.call_args[0][0]
        self.assertEqual(row_args[1], "v3.1.0")
        self.assertEqual(row_args[2], "test-actor")
        self.assertEqual(row_args[3], "gemma-plugin-3.1.0.zip")
        self.assertIn("https://github.com/GMD-Repository/gemma-plugin/releases/tag/v3.1.0", row_args[4])


if __name__ == "__main__":
    unittest.main()
