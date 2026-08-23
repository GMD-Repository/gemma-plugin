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
        # Base EA Layer (04340001 / San Mateo)
        self.ea_layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "04340_ea2024", "memory")
        pr = self.ea_layer.dataProvider()
        pr.addAttributes([
            QgsField("GEOCODE", QVariant.String),
            QgsField("EA_NO", QVariant.String),
            QgsField("CITYMUN", QVariant.String),
            QgsField("HH_COUNT", QVariant.Int),
        ])
        self.ea_layer.updateFields()

        # EA 1: (0,0) to (100,100)
        feat1 = QgsFeature(self.ea_layer.fields())
        feat1.setGeometry(make_square(0, 0, 100))
        feat1.setAttributes(["0434000001", "001", "San Mateo", 150])

        # EA 2: (100,0) to (200,100)
        feat2 = QgsFeature(self.ea_layer.fields())
        feat2.setGeometry(make_square(100, 0, 100))
        feat2.setAttributes(["0434000002", "002", "San Mateo", 200])

        pr.addFeatures([feat1, feat2])
        self.ea_layer.updateExtents()

        # Replacement Layer 1: 14 digits (01001000000001), replaces (20,20) to (80,80)
        self.repl_layer1 = QgsVectorLayer("Polygon?crs=EPSG:3857", "01001000000001", "memory")
        rpr1 = self.repl_layer1.dataProvider()
        rfeat1 = QgsFeature(self.repl_layer1.fields())
        rfeat1.setGeometry(make_square(20, 20, 60))
        rpr1.addFeatures([rfeat1])
        self.repl_layer1.updateExtents()

    def test_14_digit_layer_name_validation(self):
        """Test 14-digit numeric layer name validation rules."""
        valid_names = ["01001000000001", "01001000000002", "17501000000001"]
        invalid_names = ["010010000001", "010010000000001", "01001000000001_A", "01001_000000001", "ABC01001000000001"]

        for name in valid_names:
            self.assertTrue(bool(_REPLACEMENT_NAME_RE.match(name)), f"Should be valid: {name}")

        for name in invalid_names:
            self.assertFalse(bool(_REPLACEMENT_NAME_RE.match(name)), f"Should be invalid: {name}")

    def test_processor_runs_and_merges_replacement_polygons(self):
        """Test full merge workflow: EA subtraction + replacement addition."""
        with tempfile.TemporaryDirectory() as tmpdir:
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

    def test_invalid_replacement_layer_name_fails(self):
        """Test that invalid 14-digit replacement layer names cause validation failure."""
        invalid_layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "01001000000001_A", "memory")
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
        self.assertIn("14-digit", result.error_message)


if __name__ == "__main__":
    unittest.main()
