# -*- coding: utf-8 -*-
"""
Unit test module for CBMS MV _save_csv_changes and updated_variables tracking.
Verifies:
- _save_csv_changes updates CSV row attributes on disk
- updated_variables column records pipe-delimited modified column names
- Subsequent saves accumulate column names without duplicates
"""

import os
import csv
import tempfile
import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed

setup_qgis_mock_if_needed()


class TestCbmsMvSaveChanges(unittest.TestCase):
    """Test suite for CBMS MV CSV saving and updated_variables tracking."""

    def setUp(self):
        self.dialog_mod = importlib.import_module("references.cbms_mv.cbmsmv_dialog")

    def test_save_csv_changes_records_updated_variables(self):
        """Verify _save_csv_changes writes edited column names to updated_variables."""
        # Create a temporary CSV file
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False, suffix=".csv") as f:
            writer = csv.writer(f)
            writer.writerow(["fid", "map_uuid", "barangay_code", "ean", "remarks", "updated_variables"])
            writer.writerow(["1", "uuid-001", "001", "001", "original note", ""])
            writer.writerow(["2", "uuid-002", "002", "002", "original note 2", ""])
            temp_csv_path = f.name

        try:
            class MockFileWidget:
                def __init__(self, path):
                    self._path = path
                def filePath(self):
                    return self._path

            # Create mock dialog instance
            dialog = self.dialog_mod.CbmsmvDialog.__new__(self.dialog_mod.CbmsmvDialog)
            dialog.file_form2 = MockFileWidget(temp_csv_path)
            dialog.project = None

            # 1. Edit barangay_code on row 1
            dialog._pending_json_edits = {
                "fid_1": {
                    "df_fid": "1",
                    "uuid": "uuid-001",
                    "props": {"barangay_code": "099"},
                }
            }

            ok, count, msg = dialog._save_csv_changes()
            self.assertTrue(ok)
            self.assertEqual(count, 1)

            # Check CSV content on disk
            with open(temp_csv_path, "r", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            header = rows[0]
            row1 = rows[1]
            uv_idx = header.index("updated_variables")
            bg_idx = header.index("barangay_code")
            self.assertEqual(row1[bg_idx], "099")
            self.assertEqual(row1[uv_idx], "barangay_code")

            # 2. Second edit: edit ean on row 1
            dialog._pending_json_edits = {
                "fid_1": {
                    "df_fid": "1",
                    "uuid": "uuid-001",
                    "props": {"ean": "088"},
                }
            }

            ok, count, msg = dialog._save_csv_changes()
            self.assertTrue(ok)

            with open(temp_csv_path, "r", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            row1 = rows[1]
            ean_idx = header.index("ean")
            self.assertEqual(row1[ean_idx], "088")
            self.assertEqual(row1[uv_idx], "barangay_code|ean")

            # 3. Third edit: edit barangay_code again (should not duplicate in updated_variables)
            dialog._pending_json_edits = {
                "fid_1": {
                    "df_fid": "1",
                    "uuid": "uuid-001",
                    "props": {"barangay_code": "077"},
                }
            }

            ok, count, msg = dialog._save_csv_changes()
            self.assertTrue(ok)

            with open(temp_csv_path, "r", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            row1 = rows[1]
            self.assertEqual(row1[bg_idx], "077")
            self.assertEqual(row1[uv_idx], "barangay_code|ean")

        finally:
            if os.path.exists(temp_csv_path):
                os.remove(temp_csv_path)

    def test_save_csv_changes_creates_missing_updated_variables_column(self):
        """Verify _save_csv_changes dynamically creates updated_variables if not present in CSV."""
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False, suffix=".csv") as f:
            writer = csv.writer(f)
            writer.writerow(["fid", "map_uuid", "city_mun_code", "remarks"])
            writer.writerow(["1", "uuid-101", "01", "old remark"])
            temp_csv_path = f.name

        try:
            class MockFileWidget:
                def __init__(self, path): self._path = path
                def filePath(self): return self._path

            dialog = self.dialog_mod.CbmsmvDialog.__new__(self.dialog_mod.CbmsmvDialog)
            dialog.file_form2 = MockFileWidget(temp_csv_path)
            dialog.project = None

            dialog._pending_json_edits = {
                "fid_1": {
                    "df_fid": "1",
                    "uuid": "uuid-101",
                    "props": {"city_mun_code": "02", "remarks": "new remark"},
                }
            }

            ok, count, msg = dialog._save_csv_changes()
            self.assertTrue(ok)

            with open(temp_csv_path, "r", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            header = rows[0]
            row1 = rows[1]
            self.assertIn("updated_variables", header)
            uv_idx = header.index("updated_variables")
            self.assertEqual(row1[uv_idx], "city_mun_code|remarks")
        finally:
            if os.path.exists(temp_csv_path):
                os.remove(temp_csv_path)

    def test_save_csv_changes_windows_permission_error_fallback(self):
        """Verify _save_csv_changes falls back to direct write when os.replace raises PermissionError."""
        from unittest.mock import patch

        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False, suffix=".csv") as f:
            writer = csv.writer(f)
            writer.writerow(["fid", "map_uuid", "barangay_code", "updated_variables"])
            writer.writerow(["1", "uuid-201", "001", ""])
            temp_csv_path = f.name

        try:
            class MockFileWidget:
                def __init__(self, path): self._path = path
                def filePath(self): return self._path

            dialog = self.dialog_mod.CbmsmvDialog.__new__(self.dialog_mod.CbmsmvDialog)
            dialog.file_form2 = MockFileWidget(temp_csv_path)
            dialog.project = None

            dialog._pending_json_edits = {
                "fid_1": {
                    "df_fid": "1",
                    "uuid": "uuid-201",
                    "props": {"barangay_code": "999"},
                }
            }

            # Simulate os.replace raising PermissionError ([WinError 5] Access is denied)
            with patch("os.replace", side_effect=PermissionError("[WinError 5] Access is denied")):
                ok, count, msg = dialog._save_csv_changes()

            self.assertTrue(ok)
            self.assertEqual(count, 1)

            with open(temp_csv_path, "r", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            header = rows[0]
            row1 = rows[1]
            bg_idx = header.index("barangay_code")
            uv_idx = header.index("updated_variables")
            self.assertEqual(row1[bg_idx], "999")
            self.assertEqual(row1[uv_idx], "barangay_code")
        finally:
            if os.path.exists(temp_csv_path):
                os.remove(temp_csv_path)


if __name__ == "__main__":
    unittest.main()


