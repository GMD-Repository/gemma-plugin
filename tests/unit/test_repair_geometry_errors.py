# -*- coding: utf-8 -*-
"""
Unit test module for repair_geometry_errors.py (gmd_scripts/repair_geometry_errors.py).
Tests polygon geometry cleaning, validation, and repair algorithm execution.
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, QgsGeometry, QgsProcessingFeedback, QgsProcessingContext
from tests.mocks.sample_data import create_sample_polygon_layer

setup_qgis_mock_if_needed()


class TestRepairGeometryErrors(unittest.TestCase):
    """Test suite for repair_geometry_errors functions and algorithm."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.repair_geometry_errors")
        self.alg = self.mod.RepairGeometryErrorsAlgorithm()
        self.sample_layer = create_sample_polygon_layer("Corrupted_Polygons", count=3)

    def test_module_import(self):
        """Verify that the module imports successfully."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.repair_geometry_errors should import successfully.")

    def test_geometry_helper_functions(self):
        """Test clean_geom and is_valid_polygon_geom on sample geometry."""
        poly_geom = QgsGeometry("Polygon")
        self.assertTrue(self.mod.is_valid_polygon_geom(poly_geom))
        cleaned = self.mod.clean_geom(poly_geom)
        self.assertIsNotNone(cleaned)

    def test_algorithm_metadata(self):
        """Test algorithm metadata methods."""
        self.assertEqual(self.alg.name(), "repairpolygongeometries")
        self.assertEqual(self.alg.groupId(), "gmdtoolkits")
        self.assertIsNotNone(self.alg.createInstance())

    def test_process_algorithm_with_sample_layer(self):
        """Test processAlgorithm execution on sample vector dataset."""
        params = {
            self.alg.INPUT: self.sample_layer,
            self.alg.REPAIR_MODE: 0,
            self.alg.OUTPUT: "TEMPORARY_OUTPUT"
        }
        context = QgsProcessingContext()
        feedback = QgsProcessingFeedback()

        res = self.alg.processAlgorithm(params, context, feedback)
        self.assertIn(self.alg.OUTPUT, res)


if __name__ == "__main__":
    unittest.main()
