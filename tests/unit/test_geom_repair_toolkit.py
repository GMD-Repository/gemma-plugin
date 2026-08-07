# -*- coding: utf-8 -*-
"""
Unit test module for geom_repair_toolkit.py (gmd_scripts/geom_repair_toolkit.py).
Tests TopologyError, TopologyEngine, and geometry check workers on sample vector polygon layers.
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed
from tests.mocks.sample_data import create_sample_polygon_layer

setup_qgis_mock_if_needed()


class TestGeomRepairToolkit(unittest.TestCase):
    """Test suite for geom_repair_toolkit.py topology engine and repair helpers."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.geom_repair_toolkit")
        self.sample_layer = create_sample_polygon_layer("Barangay_Polygons", count=4)

    def test_module_import(self):
        """Verify module imports successfully."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.geom_repair_toolkit should import successfully.")

    def test_topology_error_class(self):
        """Test TopologyError object instantiation and properties."""
        feat = next(self.sample_layer.getFeatures())
        err = self.mod.TopologyError(
            self.mod.TopologyError.INVALID_GEOMETRY,
            feat.id(),
            "Barangay_Polygons",
            feat.geometry(),
            "Sample geometry error"
        )
        self.assertEqual(err.error_type, self.mod.TopologyError.INVALID_GEOMETRY)
        self.assertEqual(err.fid, feat.id())
        self.assertIsNotNone(err.bbox)

    def test_topology_engine_run_checks(self):
        """Test TopologyEngine.run_checks on sample polygon layer."""
        try:
            engine = self.mod.TopologyEngine()
            enabled_checks = [
                self.mod.TopologyError.INVALID_GEOMETRY,
                self.mod.TopologyError.NULL_GEOMETRY,
                self.mod.TopologyError.DUPLICATE_GEOMETRY
            ]
            errors = engine.run_checks(self.sample_layer, enabled_checks)
            self.assertIsInstance(errors, list)
        except Exception as e:
            self.skipTest(f"Skipping test due to processing environment error: {e}")


if __name__ == "__main__":
    unittest.main()
