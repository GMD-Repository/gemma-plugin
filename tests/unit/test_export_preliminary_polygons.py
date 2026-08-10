# -*- coding: utf-8 -*-
"""
Unit test module for export_preliminary_polygons.py (gmd_scripts/export_preliminary_polygons.py).
Tests preliminary polygon export algorithm metadata and style post-processor using sample vector data.
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, QgsProcessingFeedback, QgsProcessingContext
from tests.mocks.sample_data import create_sample_polygon_layer

setup_qgis_mock_if_needed()


class TestExportPreliminaryPolygons(unittest.TestCase):
    """Test suite for ExportPreliminaryPolygons algorithm."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.export_preliminary_polygons")
        self.alg = self.mod.ExportPreliminaryPolygons()
        self.sample_polygon = create_sample_polygon_layer("Barangay_Polygons", count=3)

    def test_module_import(self):
        """Verify that the module imports successfully."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.export_preliminary_polygons should import successfully.")

    def test_algorithm_metadata(self):
        """Test algorithm metadata methods."""
        self.assertEqual(self.alg.name(), "export_preliminary_polygons")
        self.assertEqual(self.alg.groupId(), "1map")
        self.assertIsNotNone(self.alg.displayName())
        self.assertIsNotNone(self.alg.createInstance())

    def test_post_processor_instantiation(self):
        """Test MBIStylePostProcessor class instantiation."""
        processor = self.mod.MBIStylePostProcessor("mock_style.qml")
        self.assertEqual(processor.style_path, "mock_style.qml")


if __name__ == "__main__":
    unittest.main()
