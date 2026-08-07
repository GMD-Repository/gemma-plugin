# -*- coding: utf-8 -*-
"""
Unit test module for clip_project_layers.py (gmd_scripts/clip_project_layers.py).
Tests batch layer clipping algorithm using sample spatial layer fixtures.
"""

import unittest
import importlib
import tempfile
import os
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, QgsProcessingFeedback, QgsProcessingContext
from tests.mocks.sample_data import create_sample_polygon_layer, create_sample_point_layer, create_sample_line_layer

setup_qgis_mock_if_needed()


class TestClipProjectLayers(unittest.TestCase):
    """Test suite for clip_project_layers algorithm."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.clip_project_layers")
        self.alg = self.mod.ClipProjectLayersAlgorithm()
        self.polygon_mask = create_sample_polygon_layer("EA_Mask", count=2)
        self.point_layer = create_sample_point_layer("Buildings", count=5)
        self.line_layer = create_sample_line_layer("Roads", count=3)

    def test_module_import(self):
        """Verify that the module imports successfully."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.clip_project_layers should import successfully.")

    def test_algorithm_metadata(self):
        """Test algorithm metadata methods."""
        self.assertEqual(self.alg.name(), "clipprojectlayers")
        self.assertEqual(self.alg.groupId(), "gmdtoolkits")
        self.assertIsNotNone(self.alg.displayName())
        self.assertIsNotNone(self.alg.createInstance())

    def test_process_algorithm_with_sample_layers(self):
        """Test algorithm processAlgorithm execution with sample vector data."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            params = {
                self.alg.INPUT_VECTORS: [self.point_layer, self.line_layer],
                self.alg.MASK: self.polygon_mask,
                self.alg.BUFFER: 5.0,
                self.alg.OUTPUT_FOLDER: tmp_dir,
                self.alg.OVERWRITE: True
            }
            from qgis.core import QgsProject
            QgsProject.instance().addMapLayer(self.polygon_mask)
            QgsProject.instance().addMapLayer(self.point_layer)
            QgsProject.instance().addMapLayer(self.line_layer)

            context = QgsProcessingContext()
            if hasattr(context, "setProject"):
                context.setProject(QgsProject.instance())
            if hasattr(context, "temporaryLayerStore"):
                context.temporaryLayerStore().addMapLayer(self.polygon_mask)
                context.temporaryLayerStore().addMapLayer(self.point_layer)
                context.temporaryLayerStore().addMapLayer(self.line_layer)
            feedback = QgsProcessingFeedback()

            res = self.alg.processAlgorithm(params, context, feedback)
            self.assertIn(self.alg.OUTPUT_FOLDER, res)
            self.assertEqual(res[self.alg.OUTPUT_FOLDER], tmp_dir)
            self.assertIn('CLIPPED_COUNT', res)


if __name__ == "__main__":
    unittest.main()
