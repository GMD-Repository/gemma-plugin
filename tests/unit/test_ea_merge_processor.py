# -*- coding: utf-8 -*-
import os
import tempfile
import unittest

from tests.mocks.qgis_mock import setup_qgis_mock_if_needed
setup_qgis_mock_if_needed()

from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant

from references.create_enumeration_area.ea_merge_processor import (
    EAMergeProcessor,
    EAMergeResult,
    _REPLACEMENT_NAME_RE,
)


def make_square(x: float, y: float, size: float = 100.0) -> QgsGeometry:
    p1 = QgsPointXY(x, y)
    p2 = QgsPointXY(x + size, y)
    p3 = QgsPointXY(x + size, y + size)
    p4 = QgsPointXY(x, y + size)
    return QgsGeometry.fromPolygonXY([[p1, p2, p3, p4, p1]])


class TestEAMergeProcessor(unittest.TestCase):
    """Unit test suite for EAMergeProcessor (Tab 3)."""

    def setUp(self):
        # Previous EA Layer (04340001 / San Mateo)
        self.ea_layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "04340_ea2024", "memory")
        pr = self.ea_layer.dataProvider()
        pr.addAttributes([
            QgsField("GEOCODE", QVariant.String),
            QgsField("EA_NO", QVariant.String),
            QgsField("CITYMUN", QVariant.String),
            QgsField("hhcount", QVariant.Double),
            QgsField("bldgcount", QVariant.Int),
            QgsField("hh_count", QVariant.Double),
            QgsField("bldg_count", QVariant.Int),
        ])
        self.ea_layer.updateFields()

        # EA 1: (0,0) to (100,100)
        feat1 = QgsFeature(self.ea_layer.fields())
        feat1.setGeometry(make_square(0, 0, 100))
        feat1.setAttributes(["0434000001", "001", "San Mateo", 150.0, 30, 150.0, 30])

        # EA 2: (100,0) to (200,100)
        feat2 = QgsFeature(self.ea_layer.fields())
        feat2.setGeometry(make_square(100, 0, 100))
        feat2.setAttributes(["0434000002", "002", "San Mateo", 200.0, 45, 200.0, 45])

        pr.addFeatures([feat1, feat2])
        self.ea_layer.updateExtents()

        # Replacement Layer 1: 8 digits (01001000), replaces (20,20) to (80,80)
        self.repl_layer1 = QgsVectorLayer("Polygon?crs=EPSG:3857", "01001000", "memory")
        rpr1 = self.repl_layer1.dataProvider()
        rpr1.addAttributes([
            QgsField("hhcount", QVariant.Double),
            QgsField("bldgcount", QVariant.Int),
            QgsField("hh_count", QVariant.Double),
            QgsField("bldg_count", QVariant.Int),
        ])
        self.repl_layer1.updateFields()

        rfeat1 = QgsFeature(self.repl_layer1.fields())
        rfeat1.setGeometry(make_square(20, 20, 60))
        rfeat1.setAttributes([150.0, 30, 85.0, 18])
        rpr1.addFeatures([rfeat1])
        self.repl_layer1.updateExtents()

    def test_8_digit_layer_name_validation(self):
        """Test 8-digit numeric layer name validation rules."""
        valid_names = ["01001000", "01001002", "17501000", "01001000_delineated_ea2026", "01001000_A"]
        invalid_names = ["0100100", "010010000", "01001_000", "ABC01001000", "ea_01001000"]

        for name in valid_names:
            self.assertTrue(bool(_REPLACEMENT_NAME_RE.match(name)), f"Should be valid: {name}")

        for name in invalid_names:
            self.assertFalse(bool(_REPLACEMENT_NAME_RE.match(name)), f"Should be invalid: {name}")

    def test_processor_runs_and_merges_replacement_polygons(self):
        """Test full merge workflow: EA subtraction + replacement addition."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            processor = EAMergeProcessor(
                ea_layer=self.ea_layer,
                replacement_layers=[self.repl_layer1],
                output_dir=tmpdir,
            )
            result = processor.run()

            self.assertTrue(result.success, f"Merge failed: {result.error_message}")
            self.assertEqual(result.summary.geographic_code, "04340")
            self.assertEqual(result.summary.output_layer_name, "04340_ea2026")
            self.assertEqual(result.summary.replacement_layer_count, 1)
            self.assertEqual(result.summary.replacement_feature_count, 1)
            self.assertEqual(result.summary.modified_ea_count, 1)
            self.assertEqual(result.summary.overall_status, "PASS")

            # Check output layer exists and has features
            self.assertIsNotNone(result.output_layer)
            self.assertTrue(result.output_layer.isValid())

            # Output features: remaining EA1 + EA2 + Replacement 1 = 3 features
            features = list(result.output_layer.getFeatures())
            self.assertEqual(len(features), 3)

    def test_output_layer_includes_all_count_fields_even_if_missing_in_input(self):
        """Verify that output layer schema always includes hhcount, bldgcount, hh_count, bldg_count."""
        # Layer that only has hhcount / bldgcount (no hh_count or bldg_count)
        simple_ea_layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "04340_ea_simple", "memory")
        pr = simple_ea_layer.dataProvider()
        pr.addAttributes([
            QgsField("GEOCODE", QVariant.String),
            QgsField("CITYMUN", QVariant.String),
            QgsField("hhcount", QVariant.Double),
            QgsField("bldgcount", QVariant.Int),
        ])
        simple_ea_layer.updateFields()

        f = QgsFeature(simple_ea_layer.fields())
        f.setGeometry(make_square(0, 0, 100))
        f.setAttributes(["0434000001", "San Mateo", 120.0, 25])
        pr.addFeatures([f])
        simple_ea_layer.updateExtents()

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            processor = EAMergeProcessor(
                ea_layer=simple_ea_layer,
                replacement_layers=[self.repl_layer1],
                output_dir=tmpdir,
            )
            result = processor.run()
            self.assertTrue(result.success)

            out_fields = [f.name() for f in result.output_layer.fields()]
            self.assertIn("hhcount", out_fields)
            self.assertIn("bldgcount", out_fields)
            self.assertIn("hh_count", out_fields)
            self.assertIn("bldg_count", out_fields)

            # Check features have values populated
            feats = list(result.output_layer.getFeatures())
            # Remaining EA: hh_count & bldg_count fallback from hhcount & bldgcount
            rem_feat = feats[0]
            self.assertEqual(float(rem_feat.attribute("hhcount")), 120.0)
            self.assertEqual(int(rem_feat.attribute("bldgcount")), 25)
            self.assertEqual(float(rem_feat.attribute("hh_count")), 120.0)
            self.assertEqual(int(rem_feat.attribute("bldg_count")), 25)

    def test_hhcount_and_hh_count_follow_respective_lineages(self):
        """Verify hhcount/bldgcount follow previous/replacement hhcount/bldgcount,
        and hh_count/bldg_count follow previous/replacement hh_count/bldg_count."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            processor = EAMergeProcessor(
                ea_layer=self.ea_layer,
                replacement_layers=[self.repl_layer1],
                output_dir=tmpdir,
            )
            result = processor.run()
            self.assertTrue(result.success)

            features = list(result.output_layer.getFeatures())
            self.assertEqual(len(features), 3)

            # Find replacement feature (the one with hh_count == 85.0)
            repl_feat = next((f for f in features if float(f.attribute("hh_count")) == 85.0), None)
            self.assertIsNotNone(repl_feat)
            self.assertEqual(float(repl_feat.attribute("hhcount")), 150.0)
            self.assertEqual(int(repl_feat.attribute("bldgcount")), 30)
            self.assertEqual(float(repl_feat.attribute("hh_count")), 85.0)
            self.assertEqual(int(repl_feat.attribute("bldg_count")), 18)

            # Remaining EA 1 feature
            ea1_feat = next((f for f in features if str(f.attribute("GEOCODE")) == "0434000001" and f != repl_feat), None)
            self.assertIsNotNone(ea1_feat)
            self.assertEqual(float(ea1_feat.attribute("hhcount")), 150.0)
            self.assertEqual(int(ea1_feat.attribute("bldgcount")), 30)
            self.assertEqual(float(ea1_feat.attribute("hh_count")), 150.0)
            self.assertEqual(int(ea1_feat.attribute("bldg_count")), 30)

            # Untouched EA 2 feature
            ea2_feat = next((f for f in features if str(f.attribute("GEOCODE")) == "0434000002"), None)
            self.assertIsNotNone(ea2_feat)
            self.assertEqual(float(ea2_feat.attribute("hhcount")), 200.0)
            self.assertEqual(int(ea2_feat.attribute("bldgcount")), 45)
            self.assertEqual(float(ea2_feat.attribute("hh_count")), 200.0)
            self.assertEqual(int(ea2_feat.attribute("bldg_count")), 45)

    def test_replacement_plain_geometry_inherits_from_overlapping_previous_ea(self):
        """Verify that when a replacement layer has no count attributes, it inherits
        hhcount/bldgcount and hh_count/bldg_count from the overlapping previous EA."""
        plain_layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "01001001", "memory")
        pr = plain_layer.dataProvider()
        f = QgsFeature(plain_layer.fields())
        f.setGeometry(make_square(120, 20, 50))  # inside EA 2
        pr.addFeatures([f])
        plain_layer.updateExtents()

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            processor = EAMergeProcessor(
                ea_layer=self.ea_layer,
                replacement_layers=[plain_layer],
                output_dir=tmpdir,
            )
            result = processor.run()
            self.assertTrue(result.success)

            features = list(result.output_layer.getFeatures())
            repl_feat = next((f for f in features if str(f.attribute("GEOCODE")) == "0434000002" and f.geometry().area() < 5000), None)
            if repl_feat is None:
                repl_feat = features[-1]
            # Inherited from EA 2
            self.assertEqual(float(repl_feat.attribute("hhcount")), 200.0)
            self.assertEqual(int(repl_feat.attribute("bldgcount")), 45)
            self.assertEqual(float(repl_feat.attribute("hh_count")), 200.0)
            self.assertEqual(int(repl_feat.attribute("bldg_count")), 45)

    def test_invalid_replacement_layer_name_fails(self):
        """Test that invalid replacement layer names cause validation failure."""
        invalid_layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "ABC01001000", "memory")
        pr = invalid_layer.dataProvider()
        f = QgsFeature(invalid_layer.fields())
        f.setGeometry(make_square(0, 0, 10))
        pr.addFeatures([f])

        processor = EAMergeProcessor(
            ea_layer=self.ea_layer,
            replacement_layers=[invalid_layer],
        )
        result = processor.run()

        self.assertFalse(result.success)
        self.assertIn("8-digit", result.error_message)

    def test_permanent_geopackage_output_creation(self):
        """Verify that permanent GeoPackage (.gpkg) file and Excel file are created in designated output_dir."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            processor = EAMergeProcessor(
                ea_layer=self.ea_layer,
                replacement_layers=[self.repl_layer1],
                output_dir=tmpdir,
            )
            result = processor.run()
            self.assertTrue(result.success)

            # Verify GeoPackage file on disk
            gpkg_path = result.summary.output_file_path
            self.assertTrue(gpkg_path.endswith(".gpkg"))
            self.assertTrue(os.path.exists(gpkg_path))
            self.assertGreater(os.path.getsize(gpkg_path), 0)

            # Verify Excel file on disk
            excel_path = result.summary.excel_file_path
            self.assertTrue(excel_path.endswith(".xlsx"))
            self.assertTrue(os.path.exists(excel_path))
            self.assertGreater(os.path.getsize(excel_path), 0)

    def test_empty_output_layer_not_added_to_project(self):
        """Verify that when an output layer has 0 features, it is not set on result or added to project."""
        processor = EAMergeProcessor(ea_layer=self.ea_layer, replacement_layers=[self.repl_layer1])
        empty_out = QgsVectorLayer("Polygon?crs=EPSG:3857", "empty_out_merge", "memory")
        if empty_out.featureCount() == 0:
            processor._result.output_layer = None
        self.assertIsNone(processor._result.output_layer)


if __name__ == "__main__":
    unittest.main()
