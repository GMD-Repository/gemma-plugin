# -*- coding: utf-8 -*-
"""
Unit test module for gsheet.py (gmd_scripts/gsheet.py).
Tests module structure and safe import handling.
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed

setup_qgis_mock_if_needed()


class TestGsheet(unittest.TestCase):
    """Test suite for gsheet module."""

    def test_module_import(self):
        """Verify that the module imports successfully."""
        mod = importlib.import_module("gmd_scripts.gsheet")
        self.assertIsNotNone(mod, "Module gmd_scripts.gsheet should import successfully.")


if __name__ == "__main__":
    unittest.main()
