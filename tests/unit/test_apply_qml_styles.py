# -*- coding: utf-8 -*-
"""
Unit test module for apply_qml_styles.py (gmd_scripts/apply_qml_styles.py).
Tests QML styling and layer group organization algorithm using sample layers.
"""

import unittest
import importlib
import json
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, QgsProcessingFeedback, QgsProcessingContext
from tests.mocks.sample_data import create_sample_polygon_layer, create_sample_point_layer

setup_qgis_mock_if_needed()


class TestApplyQmlStyles(unittest.TestCase):
    """Test suite for apply_qml_styles algorithm."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.apply_qml_styles")
        self.alg = self.mod.ApplyQmlStylesAlgorithm()
        self.sample_polygon = create_sample_polygon_layer("EA_Boundaries", count=3)
        self.sample_point = create_sample_point_layer("Building_Points", count=5)

    def test_module_import(self):
        """Verify module imports successfully."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.apply_qml_styles should import successfully.")

    def test_algorithm_metadata(self):
        """Test algorithm metadata methods."""
        self.assertEqual(self.alg.name(), "applyqmlstyles")
        self.assertEqual(self.alg.groupId(), "gmdtoolkits")
        self.assertIsNotNone(self.alg.displayName())
        self.assertIsNotNone(self.alg.createInstance())

    def test_process_algorithm_with_sample_json_config(self):
        """Test processAlgorithm execution using in-memory JSON layout configuration."""
        json_config = json.dumps([
            {
                "group": "Boundaries",
                "layers": [{"name": "EA_Boundaries", "qml": "ea_boundary.qml"}]
            },
            {
                "group": "Features",
                "layers": [{"name": "Building_Points", "qml": "building.qml"}]
            }
        ])

        params = {
            self.alg.CONFIG_FILE: json_config,
            self.alg.ORGANIZE_GROUPS: True
        }
        context = QgsProcessingContext()
        feedback = QgsProcessingFeedback()

        res = self.alg.processAlgorithm(params, context, feedback)
        self.assertIn(self.alg.OUTPUT_REPORT, res)


if __name__ == "__main__":
    unittest.main()
