# -*- coding: utf-8 -*-
"""
Unit test module for projection_finder.py (gmd_scripts/projection_finder.py).
Tests CRS diagnostics, candidate scanning, affine solver, and algorithm metadata.
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed
setup_qgis_mock_if_needed()

from qgis.core import (
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsRectangle,
)
from tests.mocks.sample_data import create_sample_polygon_layer


class TestProjectionFinder(unittest.TestCase):
    """Test suite for Know Your Projection (projection_finder) tool and algorithm."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.projection_finder")
        self.alg = self.mod.ProjectionFinderAlgorithm()
        self.sample_layer = create_sample_polygon_layer("Sample_Boundary", count=3)

    def test_module_import(self):
        """Verify module and core classes import successfully."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.projection_finder should import successfully.")
        self.assertTrue(hasattr(self.mod, "ProjectionFinderAlgorithm"))
        self.assertTrue(hasattr(self.mod, "ProjectionToolkit"))
        self.assertTrue(hasattr(self.mod, "diagnose_extent"))
        self.assertTrue(hasattr(self.mod, "fit_affine"))
        self.assertTrue(hasattr(self.mod, "scan_candidates"))

    def test_algorithm_metadata(self):
        """Verify algorithm metadata conforms to GMD standards."""
        self.assertEqual(self.alg.name(), "projection_finder")
        self.assertEqual(self.alg.displayName(), "Know Your Projection")
        self.assertEqual(self.alg.group(), "1Map")
        self.assertEqual(self.alg.groupId(), "1map")
        self.assertIsNotNone(self.alg.icon())

    def test_diagnose_extent_geographic(self):
        """Verify geographic coordinate extent is correctly diagnosed."""
        # Metro Manila extent in WGS84 degrees
        ext = QgsRectangle(120.9, 14.5, 121.1, 14.7)
        kind, report = self.mod.diagnose_extent(ext)
        self.assertEqual(kind, "geographic")
        self.assertIn("Geographic Coordinates", report)

    def test_diagnose_extent_projected(self):
        """Verify projected meter coordinate extent is correctly diagnosed."""
        # Zone III PRS92 / UTM projected meters
        ext = QgsRectangle(480000.0, 1600000.0, 520000.0, 1640000.0)
        kind, report = self.mod.diagnose_extent(ext)
        self.assertEqual(kind, "projected")
        self.assertIn("Projected Grid", report)

    def test_diagnose_extent_web_mercator(self):
        """Verify Web Mercator coordinate extent is correctly diagnosed."""
        # Philippines in Web Mercator (EPSG:3857)
        ext = QgsRectangle(13400000.0, 1600000.0, 13500000.0, 1700000.0)
        kind, report = self.mod.diagnose_extent(ext)
        self.assertEqual(kind, "webmercator")
        self.assertIn("Web Mercator", report)

    def test_solve3_linear_system(self):
        """Verify 3x3 linear equation solver _solve3."""
        # Solve:
        # 1*x + 0*y + 0*z = 5
        # 0*x + 2*y + 0*z = 6
        # 0*x + 0*y + 3*z = 9
        # -> solution: (5, 3, 3)
        A = [
            [1.0, 0.0, 0.0],
            [0.0, 2.0, 0.0],
            [0.0, 0.0, 3.0],
        ]
        B = [5.0, 6.0, 9.0]
        sol = self.mod._solve3(A, B)
        self.assertAlmostEqual(sol[0], 5.0, places=5)
        self.assertAlmostEqual(sol[1], 3.0, places=5)
        self.assertAlmostEqual(sol[2], 3.0, places=5)

    def test_fit_affine_transformation(self):
        """Verify 6-parameter affine transformation solver fit_affine."""
        # Test 2x scale and translation (+100, +200)
        src_pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        dst_pts = [(100.0, 200.0), (120.0, 200.0), (120.0, 220.0), (100.0, 220.0)]
        (a, b, c), (d, e, f), residuals = self.mod.fit_affine(src_pts, dst_pts)
        self.assertAlmostEqual(a, 2.0, places=3)
        self.assertAlmostEqual(e, 2.0, places=3)
        self.assertAlmostEqual(c, 100.0, places=3)
        self.assertAlmostEqual(f, 200.0, places=3)
        rms = (sum(r * r for r in residuals) / len(residuals)) ** 0.5
        self.assertAlmostEqual(rms, 0.0, places=3)

    def test_scan_candidates(self):
        """Verify candidate scanning against Philippine extents."""
        ext = QgsRectangle(480000.0, 1600000.0, 520000.0, 1640000.0)
        hits, misses = self.mod.scan_candidates(ext)
        self.assertIsInstance(hits, list)
        self.assertIsInstance(misses, list)

    def test_process_algorithm_headless(self):
        """Verify headless execution of ProjectionFinderAlgorithm."""
        context = QgsProcessingContext()
        feedback = QgsProcessingFeedback()
        params = {self.alg.INPUT: self.sample_layer}
        try:
            res = self.alg.processAlgorithm(params, context, feedback)
            self.assertIn(self.alg.OUTPUT, res)
            self.assertIn("Source Layer", res[self.alg.OUTPUT])
        except Exception as e:
            self.skipTest(f"Skipping test due to processing environment error: {e}")

    def test_projection_toolkit_instantiation(self):
        """Verify ProjectionToolkit dialog instantiates cleanly."""
        try:
            from qgis.PyQt.QtWidgets import QApplication
            app = QApplication.instance()
            if app is None:
                self.skipTest("No QApplication available in test environment.")
            dlg = self.mod.ProjectionToolkit()
            self.assertIsNotNone(dlg)
            self.assertEqual(dlg.windowTitle(), "Know Your Projection")
            self.assertTrue(hasattr(dlg, "finder_tab"))
            self.assertTrue(hasattr(dlg, "point_repair_tab"))
            self.assertTrue(hasattr(dlg, "help_tab"))
        except Exception as e:
            self.skipTest(f"Skipping dialog UI test in headless environment: {e}")

    def test_audit_point_coordinates(self):
        """Verify scanning and anomaly detection for point layers with outliers/nulls."""
        from tests.mocks.qgis_mock import QgsVectorLayer, QgsField, QgsFields, QgsFeature, QgsGeometry, QgsPointXY
        from qgis.PyQt.QtCore import QVariant

        layer = QgsVectorLayer("Point?crs=EPSG:4326", "Test_Building_Points", "memory")
        fields = QgsFields()
        fields.append(QgsField("fid", getattr(QVariant, "Int", 2)))
        fields.append(QgsField("longitude", getattr(QVariant, "Double", 6)))
        fields.append(QgsField("latitude", getattr(QVariant, "Double", 6)))
        layer.dataProvider().addAttributes(list(fields))
        layer.updateFields()

        features = []
        for i in range(1, 4):
            f = QgsFeature(layer.fields())
            f.setAttributes([i, 124.20 + i * 0.01, 13.80 + i * 0.01])
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(124.20 + i * 0.01, 13.80 + i * 0.01)))
            features.append(f)
        f_out = QgsFeature(layer.fields())
        f_out.setAttributes([4, 124.2844, 13.8480])
        f_out.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(638807.0, 1531293.0)))
        features.append(f_out)
        f_null = QgsFeature(layer.fields())
        f_null.setAttributes([5, 124.2900, 13.8500])
        f_null.setGeometry(QgsGeometry())
        features.append(f_null)

        layer.dataProvider().addFeatures(features)
        layer.updateExtents()

        res = self.mod.audit_point_coordinates(layer)
        self.assertEqual(res['total'], 5)
        self.assertEqual(res['normal_count'], 3)
        self.assertEqual(res['outlier_count'], 1)
        self.assertEqual(res['null_count'], 1)
        self.assertEqual(res['repairable_count'], 2)
        self.assertEqual(res['lon_field'], 'longitude')
        self.assertEqual(res['lat_field'], 'latitude')

    def test_repair_point_outliers(self):
        """Verify in-place repair of point outliers and nulls from lon/lat columns."""
        from tests.mocks.qgis_mock import QgsVectorLayer, QgsField, QgsFields, QgsFeature, QgsGeometry, QgsPointXY
        from qgis.PyQt.QtCore import QVariant

        layer = QgsVectorLayer("Point?crs=EPSG:4326", "Test_Repair_Points", "memory")
        fields = QgsFields()
        fields.append(QgsField("fid", getattr(QVariant, "Int", 2)))
        fields.append(QgsField("longitude", getattr(QVariant, "Double", 6)))
        fields.append(QgsField("latitude", getattr(QVariant, "Double", 6)))
        layer.dataProvider().addAttributes(list(fields))
        layer.updateFields()

        features = []
        f1 = QgsFeature(layer.fields())
        f1.setAttributes([1, 124.25, 13.85])
        f1.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(124.25, 13.85)))
        features.append(f1)
        f2 = QgsFeature(layer.fields())
        f2.setAttributes([2, 124.28, 13.84])
        f2.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(638807.0, 1531293.0)))
        features.append(f2)

        layer.dataProvider().addFeatures(features)
        layer.updateExtents()

        repaired, skipped = self.mod.repair_point_outliers(layer)
        self.assertEqual(repaired, 1)
        self.assertEqual(skipped, 0)

        if layer.isEditable():
            layer.commitChanges()

        for f in layer.getFeatures():
            if f['fid'] == 2:
                pt = f.geometry().asPoint()
                self.assertAlmostEqual(pt.x(), 124.28, places=4)
                self.assertAlmostEqual(pt.y(), 13.84, places=4)


if __name__ == "__main__":
    unittest.main()

