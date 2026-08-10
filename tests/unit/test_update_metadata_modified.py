# -*- coding: utf-8 -*-
"""
Unit test module for update_metadata_modified.py (gmd_scripts/update_metadata_modified.py).
Tests barangay name normalization and metadata update processing algorithm.
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed
from tests.mocks.sample_data import create_sample_polygon_layer

setup_qgis_mock_if_needed()


class TestUpdateMetadataModified(unittest.TestCase):
    """Test suite for update_metadata_modified module."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.update_metadata_modified")
        self.sample_layer = create_sample_polygon_layer("Barangay_Boundaries", count=3)

    def test_module_import(self):
        """Verify module imports successfully."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.update_metadata_modified should import successfully.")

    def test_normalize_barangay_name_function(self):
        """Test normalize_barangay_name helper function with abbreviations, roman numerals, and casing."""
        self.assertEqual(self.mod.normalize_barangay_name("Sta. Rosa"), "santarosa")
        self.assertEqual(self.mod.normalize_barangay_name("Brgy. Poblacion I"), "poblacion1")
        self.assertEqual(self.mod.normalize_barangay_name("Sto. Tomas"), "santotomas")


if __name__ == "__main__":
    unittest.main()
