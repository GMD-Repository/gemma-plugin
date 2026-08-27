# -*- coding: utf-8 -*-
"""
Unit test module for update_metadata.py (gmd_scripts/update_metadata.py).
Tests barangay name normalization, 2024 Barangay Layers count lookup, and metadata update processing algorithm.
"""

import os
import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed
from tests.mocks.sample_data import create_sample_polygon_layer

setup_qgis_mock_if_needed()


class TestUpdateMetadata(unittest.TestCase):
    """Test suite for update_metadata module."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.update_metadata")
        self.sample_layer = create_sample_polygon_layer("Barangay_Boundaries", count=3)

    def test_module_import(self):
        """Verify module imports successfully."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.update_metadata should import successfully.")

    def test_normalize_barangay_name_function(self):
        """Test normalize_barangay_name helper function with abbreviations, roman numerals, and casing."""
        self.assertEqual(self.mod.normalize_barangay_name("Sta. Rosa"), "santarosa")
        self.assertEqual(self.mod.normalize_barangay_name("Brgy. Poblacion I"), "poblacion1")
        self.assertEqual(self.mod.normalize_barangay_name("Sto. Tomas"), "santotomas")

    def test_normalize_admin_name_function(self):
        """Test normalize_admin_name helper function for province and municipality normalization."""
        self.assertEqual(self.mod.normalize_admin_name("City of Manila"), "manila")
        self.assertEqual(self.mod.normalize_admin_name("Province of Abra"), "abra")
        self.assertEqual(self.mod.normalize_admin_name("City of Cebu (Capital)"), "cebu")
        self.assertEqual(self.mod.normalize_admin_name("NCR, First District"), "")

    def test_get_2024_barangay_layers_dir(self):
        """Test locating the 2024 Barangay Layers reference directory."""
        ref_dir = self.mod.get_2024_barangay_layers_dir()
        self.assertIsNotNone(ref_dir, "Should find the 2024 Barangay Layers directory.")
        self.assertTrue(os.path.exists(ref_dir), f"Directory '{ref_dir}' should exist.")

    def test_barangay_count_lookup_discovery_and_extraction(self):
        """Test BarangayCountLookup loading and extraction of hhcount and bldgcount."""
        lookup = self.mod.BarangayCountLookup()

        # Test Bangued, Abra
        hh, bldg = lookup.get_counts("Abra", "Bangued", "Zone 7 Pob.")
        self.assertIsNotNone(hh, "hhcount for Zone 7 Pob. should not be None.")
        self.assertIsNotNone(bldg, "bldgcount for Zone 7 Pob. should not be None.")
        self.assertEqual(hh, 567)
        self.assertEqual(bldg, 580)

        # Test by UUID
        hh_uuid, bldg_uuid = lookup.get_counts(
            "Abra", "Bangued", map_uuid="73fd9b14-bf80-4f01-98c2-ff5b95d674ff"
        )
        self.assertEqual(hh_uuid, 567)
        self.assertEqual(bldg_uuid, 580)

        # Test by Geocode
        hh_geo, bldg_geo = lookup.get_counts(
            "Abra", "Bangued", geocode="00101030000000"
        )
        self.assertEqual(hh_geo, 567)
        self.assertEqual(bldg_geo, 580)

        # Test Atok, Benguet
        hh_atok, bldg_atok = lookup.get_counts("Benguet", "Atok", "Abiang")
        self.assertEqual(hh_atok, 553)
        self.assertEqual(bldg_atok, 540)

        # Test Binondo, City of Manila
        hh_mnl, bldg_mnl = lookup.get_counts("City of Manila", "Binondo", "Barangay 295")
        self.assertEqual(hh_mnl, 446)
        self.assertEqual(bldg_mnl, 51)

        # Test non-existent barangay returns (None, None)
        hh_none, bldg_none = lookup.get_counts("Abra", "Bangued", "Nonexistent Barangay")
        self.assertIsNone(hh_none)
        self.assertIsNone(bldg_none)


if __name__ == "__main__":
    unittest.main()
