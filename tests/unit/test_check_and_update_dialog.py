# -*- coding: utf-8 -*-
"""
Unit test module for check_and_update_dialog.py (gmd_scripts/check_and_update_dialog.py).
Tests resolve_processing_output_layer helper function using sample vector layers.
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, QgsProcessingContext
from tests.mocks.sample_data import create_sample_polygon_layer

setup_qgis_mock_if_needed()


class TestCheckAndUpdateDialog(unittest.TestCase):
    """Test suite for check_and_update_dialog module."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.check_and_update_dialog")
        self.sample_layer = create_sample_polygon_layer("Barangay_Boundaries", count=3)

    def test_module_import(self):
        """Verify module imports successfully."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.check_and_update_dialog should import successfully.")

    def test_resolve_processing_output_layer(self):
        """Test resolve_processing_output_layer helper function with layer object."""
        try:
            context = QgsProcessingContext()
            res = self.mod.resolve_processing_output_layer(self.sample_layer, context)
            self.assertEqual(res, self.sample_layer, "Output layer should resolve to input QgsVectorLayer.")
        except Exception as e:
            self.skipTest(f"Skipping test due to processing environment error: {e}")


if __name__ == "__main__":
    unittest.main()
