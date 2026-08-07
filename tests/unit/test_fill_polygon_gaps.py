# -*- coding: utf-8 -*-
"""
Unit test module for fill_polygon_gaps.py (gmd_scripts/fill_polygon_gaps.py).
Tests polygon gap filling algorithm using sample vector data fixtures.
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, QgsProcessingFeedback, QgsProcessingContext, MockGenericClass
from tests.mocks.sample_data import create_sample_polygon_layer

setup_qgis_mock_if_needed()


class TestFillPolygonGaps(unittest.TestCase):
    """Test suite for fill_polygon_gaps algorithm."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.fill_polygon_gaps")
        self.alg = self.mod.FillPolygonGapsAlgorithm()
        self.sample_layer = create_sample_polygon_layer("EA_Gap_Polygons", count=5)

    def test_module_import(self):
        """Verify that the module imports successfully."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.fill_polygon_gaps should import successfully.")

    def test_algorithm_metadata(self):
        """Test algorithm metadata and instantiation."""
        self.assertEqual(self.alg.name(), "fillpolygongaps")
        self.assertEqual(self.alg.groupId(), "gmdtoolkits")
        self.assertIsNotNone(self.alg.displayName())
        self.assertIsNotNone(self.alg.createInstance())

    def test_find_target_feature_on_sample_data(self):
        """Test target feature search using sample polygon layer and field filter."""
        feedback = QgsProcessingFeedback()
        # Find feature with ea_code='0517370001001'
        if hasattr(self.alg, "_find_target_feature"):
            target = self.alg._find_target_feature(
                self.sample_layer, MockGenericClass(), "ea_code", "0517370001001", feedback
            )
            self.assertIsNotNone(target, "Should locate target feature with code 0517370001001.")


if __name__ == "__main__":
    unittest.main()
