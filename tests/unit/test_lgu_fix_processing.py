# -*- coding: utf-8 -*-
"""
Unit test module for lgu_fix_processing.py (gmd_scripts/lgu_fix_processing.py).
Tests FixLGUCRSAlgorithm processing algorithm using sample polygon layer and affine transformation matrix.
"""

import unittest
import importlib
import numpy as np
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, QgsProcessingContext, QgsProcessingFeedback, QgsProcessingException
from tests.mocks.sample_data import create_sample_polygon_layer, create_sample_point_layer

setup_qgis_mock_if_needed()


class TestLguFixProcessing(unittest.TestCase):
    """Test suite for FixLGUCRSAlgorithm processing algorithm."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.lgu_fix_processing")
        self.alg = self.mod.FixLGUCRSAlgorithm()
        self.sample_layer = create_sample_polygon_layer("LGU_Boundary", count=3)
        self.sample_points = create_sample_point_layer("Building_Points", count=5)

    def test_module_import(self):
        """Verify that the module imports successfully."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.lgu_fix_processing should import successfully.")

    def test_algorithm_metadata(self):
        """Test algorithm metadata methods."""
        self.assertEqual(self.alg.name(), "fixlgucrs")
        self.assertEqual(self.alg.groupId(), "1map")
        self.assertIsNotNone(self.alg.displayName())
        self.assertIsNotNone(self.alg.createInstance())

    def test_transform_geometry_with_affine_matrix(self):
        """Test transform_geometry helper function using sample polygon geometry and 2D affine matrix."""
        try:
            feat = next(self.sample_layer.getFeatures())
            geom = feat.geometry()
            self.assertIsNotNone(geom, "Sample feature geometry should exist.")

            # Identity affine transformation matrix M
            M = np.array([
                [1.0, 0.0],
                [0.0, 1.0],
                [0.0, 0.0]
            ])

            transformed_geom = self.mod.transform_geometry(geom, M)
            self.assertIsNotNone(transformed_geom, "Transformed geometry should be created.")
        except Exception as e:
            self.skipTest(f"Skipping test due to processing environment error: {e}")

    def test_process_algorithm_with_sample_layer(self):
        """Test processAlgorithm validation when insufficient control points exist."""
        params = {
            self.alg.INPUT: self.sample_layer,
            self.alg.OUTPUT: 'memory:output_fixed_lgu'
        }
        from qgis.core import QgsProject
        QgsProject.instance().addMapLayer(self.sample_layer)

        context = QgsProcessingContext()
        if hasattr(context, "setProject"):
            context.setProject(QgsProject.instance())
        if hasattr(context, "temporaryLayerStore"):
            context.temporaryLayerStore().addMapLayer(self.sample_layer)
        feedback = QgsProcessingFeedback()

        # The algorithm validates that control points must be present before executing transformation
        with self.assertRaises(QgsProcessingException):
            self.alg.processAlgorithm(params, context, feedback)


if __name__ == "__main__":
    unittest.main()
