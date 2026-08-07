# -*- coding: utf-8 -*-
"""
Unit test module for scan_geometry_errors.py (gmd_scripts/scan_geometry_errors.py).
Tests geometry and topology error scanner algorithm on sample vector data fixtures.
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, QgsProcessingFeedback, QgsProcessingContext
from tests.mocks.sample_data import create_sample_polygon_layer

setup_qgis_mock_if_needed()


class TestScanGeometryErrors(unittest.TestCase):
    """Test suite for scan_geometry_errors algorithm."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.scan_geometry_errors")
        self.alg = self.mod.ScanGeometryErrorsAlgorithm()
        self.sample_layer = create_sample_polygon_layer("EA_Scan_Polygons", count=5)

    def test_module_import(self):
        """Verify that the module imports successfully."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.scan_geometry_errors should import successfully.")

    def test_algorithm_metadata(self):
        """Test algorithm metadata methods."""
        self.assertEqual(self.alg.name(), "scangeometryerrors")
        self.assertEqual(self.alg.groupId(), "gmdtoolkits")
        self.assertIsNotNone(self.alg.displayName())
        self.assertIsNotNone(self.alg.createInstance())

    def test_process_algorithm_with_sample_layer(self):
        """Test processAlgorithm execution on sample vector dataset."""
        params = {
            self.alg.INPUT: self.sample_layer,
            self.alg.CHECK_NULL: True,
            self.alg.CHECK_EMPTY: True,
            self.alg.CHECK_INVALID: True,
            self.alg.CHECK_SELF_INTERSECT: True,
            self.alg.CHECK_WRONG_TYPE: True,
            self.alg.CHECK_DUPLICATE: False,
            self.alg.OUTPUT_ERRORS: "TEMPORARY_OUTPUT"
        }
        from qgis.core import QgsProject
        QgsProject.instance().addMapLayer(self.sample_layer)

        context = QgsProcessingContext()
        if hasattr(context, "setProject"):
            context.setProject(QgsProject.instance())
        if hasattr(context, "temporaryLayerStore"):
            context.temporaryLayerStore().addMapLayer(self.sample_layer)
        feedback = QgsProcessingFeedback()

        res = self.alg.processAlgorithm(params, context, feedback)
        self.assertIn(self.alg.OUTPUT_ERRORS, res)


if __name__ == "__main__":
    unittest.main()
