# -*- coding: utf-8 -*-
"""
Unit test module for update_metadata.py (gmd_scripts/update_metadata.py).
Tests barangay name normalization and metadata update processing algorithm.
"""

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

    def test_psgc_field_mapping_includes_counts(self):
        """Test that _get_psgc_field_mapping accurately detects hhcount and bldgcount columns."""
        alg = self.mod.UpdateLguPsgcMetadataAlgorithm()
        from tests.mocks.qgis_mock import QgsFields, QgsField, MockQVariant
        try:
            from PyQt5.QtCore import QVariant
        except Exception:
            QVariant = MockQVariant

        fields = QgsFields()
        fields.append(QgsField("map_uuid", getattr(QVariant, "String", 1)))
        fields.append(QgsField("geocode", getattr(QVariant, "String", 1)))
        fields.append(QgsField("region", getattr(QVariant, "String", 1)))
        fields.append(QgsField("province", getattr(QVariant, "String", 1)))
        fields.append(QgsField("city_mun", getattr(QVariant, "String", 1)))
        fields.append(QgsField("barangay", getattr(QVariant, "String", 1)))
        fields.append(QgsField("hhcount", getattr(QVariant, "Int", 2)))
        fields.append(QgsField("bldgcount", getattr(QVariant, "Int", 2)))

        mapping = alg._get_psgc_field_mapping(fields)
        self.assertIn("hhcount", mapping)
        self.assertEqual(mapping["hhcount"], "hhcount")
        self.assertIn("bldgcount", mapping)
        self.assertEqual(mapping["bldgcount"], "bldgcount")

    def test_psgc_field_mapping_alias_variations(self):
        """Test that field aliases such as hh_count and total_bldgcount map properly."""
        alg = self.mod.UpdateLguPsgcMetadataAlgorithm()
        from tests.mocks.qgis_mock import QgsFields, QgsField, MockQVariant
        try:
            from PyQt5.QtCore import QVariant
        except Exception:
            QVariant = MockQVariant

        fields = QgsFields()
        fields.append(QgsField("geocode", getattr(QVariant, "String", 1)))
        fields.append(QgsField("region", getattr(QVariant, "String", 1)))
        fields.append(QgsField("province", getattr(QVariant, "String", 1)))
        fields.append(QgsField("city_mun", getattr(QVariant, "String", 1)))
        fields.append(QgsField("barangay", getattr(QVariant, "String", 1)))
        fields.append(QgsField("hh_count", getattr(QVariant, "Int", 2)))
        fields.append(QgsField("total_bldgcount", getattr(QVariant, "Int", 2)))

        mapping = alg._get_psgc_field_mapping(fields)
        self.assertEqual(mapping.get("hhcount"), "hh_count")
        self.assertEqual(mapping.get("bldgcount"), "total_bldgcount")


if __name__ == "__main__":
    unittest.main()
