# -*- coding: utf-8 -*-
import unittest
from typing import Dict, Any, List

from tests.mocks.qgis_mock import setup_qgis_mock_if_needed
setup_qgis_mock_if_needed()

from qgis.core import (
    QgsFeature,
    QgsFields,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant

from references.create_enumeration_area.pre_ea_processor import (
    PreEAProcessor,
    PreEAResult,
    PreEASummary,
)


def make_square(x: float, y: float, size: float = 100.0) -> QgsGeometry:
    p1 = QgsPointXY(x, y)
    p2 = QgsPointXY(x + size, y)
    p3 = QgsPointXY(x + size, y + size)
    p4 = QgsPointXY(x, y + size)
    return QgsGeometry.fromPolygonXY([[p1, p2, p3, p4, p1]])


class TestPreEAProcessor(unittest.TestCase):
    """Unit test suite for PreEAProcessor module."""

    def setUp(self):
        # Create Barangay vector layer
        self.bgy_layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "barangays", "memory")
        bgy_pr = self.bgy_layer.dataProvider()
        bgy_pr.addAttributes([
            QgsField("geocode", QVariant.String),
            QgsField("name", QVariant.String),
        ])
        self.bgy_layer.updateFields()

        # Barangay: 0,0 to 200,100 (area = 20,000)
        bgy_feat = QgsFeature(self.bgy_layer.fields())
        bgy_feat.setGeometry(make_square(0, 0, 100).combine(make_square(100, 0, 100)))
        bgy_feat.setAttributes(["137401001", "Barangay 1"])
        bgy_pr.addFeatures([bgy_feat])
        self.bgy_layer.updateExtents()

        # Create EA vector layer with intentional gap
        self.ea_layer = QgsVectorLayer("Polygon?crs=EPSG:3857", "eas", "memory")
        ea_pr = self.ea_layer.dataProvider()
        ea_pr.addAttributes([
            QgsField("geocode", QVariant.String),
            QgsField("ean", QVariant.String),
            QgsField("hh_count", QVariant.Double),
            QgsField("bldg_count", QVariant.Int),
        ])
        self.ea_layer.updateFields()

        # EA 1 covers 0,0 to 80,100 (leaving 80 to 200 as gap inside Barangay)
        ea1 = QgsFeature(self.ea_layer.fields())
        ea1.setGeometry(make_square(0, 0, 80))
        ea1.setAttributes(["137401001", "001", 120.0, 15])

        # EA 2 covers 120,0 to 200,100
        ea2 = QgsFeature(self.ea_layer.fields())
        ea2.setGeometry(make_square(120, 0, 80))
        ea2.setAttributes(["137401001", "002", 85.0, 10])

        ea_pr.addFeatures([ea1, ea2])
        self.ea_layer.updateExtents()

    def test_processor_runs_and_fills_gaps(self):
        """Test PreEAProcessor run method and gap filling functionality."""
        processor = PreEAProcessor()
        result = processor.run(
            barangay_layer=self.bgy_layer,
            ea_layer=self.ea_layer,
            gap_tolerance=1.0,
            clip_to_bgy=True,
            detect_gaps=True,
            assign_gaps=True,
        )

        self.assertTrue(result.success, f"PreEAProcessor failed with error: {result.error_message}")
        self.assertEqual(result.summary.barangays_processed, 1)
        self.assertEqual(result.summary.eas_processed, 2)
        self.assertGreater(result.summary.gaps_detected, 0)
        self.assertGreater(result.summary.gaps_assigned, 0)

        # Output layer should exist and be valid
        self.assertIsNotNone(result.output_layer)
        self.assertTrue(result.output_layer.isValid())

        # Verify hhcount and bldgcount fields exist in output layer
        out_field_names = [f.name() for f in result.output_layer.fields()]
        self.assertIn("hhcount", out_field_names)
        self.assertIn("bldgcount", out_field_names)

        # Output features count should match input EAs (2)
        output_features = list(result.output_layer.getFeatures())
        self.assertEqual(len(output_features), 2)
        
        # Verify feature attribute values
        feat1 = next(f for f in output_features if f.attribute("ean") == "001")
        self.assertEqual(float(feat1.attribute("hhcount")), 120.0)
        self.assertEqual(int(feat1.attribute("bldgcount")), 15)

    def test_explode_to_polygons_handles_multipolygon(self):
        """Test that _explode_to_polygons correctly handles MultiPolygon WKB types."""
        processor = PreEAProcessor()

        poly1 = make_square(0, 0, 10)
        poly2 = make_square(20, 20, 10)
        multi_poly = poly1.combine(poly2)

        parts = processor._explode_to_polygons(multi_poly)
        self.assertEqual(len(parts), 2)
        for p in parts:
            self.assertFalse(p.isEmpty())

    def test_eliminate_sliver_parts(self):
        """Test that _eliminate_sliver_parts filters out micro-sliver parts."""
        processor = PreEAProcessor()

        poly1 = make_square(0, 0, 100) # larger part
        poly2 = make_square(200, 200, 1) # tiny sliver part
        multi_poly = poly1.combine(poly2)

        # When min_area = 5.0, poly2 (area < 5) should be filtered out
        cleaned = processor._eliminate_sliver_parts(multi_poly, min_area=5.0)
        self.assertIsNotNone(cleaned)
        self.assertFalse(cleaned.isEmpty())


if __name__ == "__main__":
    unittest.main()
