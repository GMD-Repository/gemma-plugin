# -*- coding: utf-8 -*-
"""
Unit test module for CBMS MV Fix: Copy Geometry to Longitude and Latitude columns.
Verifies:
- Copying geometry point coordinates (X -> longitude, Y -> latitude) formatted to 7 decimals
- Updating sf_longitude and sf_latitude attributes on vector layer
- Adding sf_longitude and sf_latitude fields if not originally present
- Updating standard longitude and latitude columns if present
- run_fix dispatcher routing for copy_geometry_to_coordinates and aliases
- UI dropdown item registration in combo_actions and _on_copy_geometry_to_coordinates delegation
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsFields,
    QgsField,
    QgsGeometry,
    QgsPointXY,
)
from qgis.PyQt.QtCore import QVariant

setup_qgis_mock_if_needed()


class TestCbmsMvCopyGeometryFix(unittest.TestCase):
    """Test suite for copying geometry to longitude and latitude columns."""

    def setUp(self):
        self.fix_mod = importlib.import_module("references.cbms_mv.cbms_mv_fix.cbms_mv_fix")
        self.dialog_mod = importlib.import_module("references.cbms_mv.cbmsmv_dialog")

    def test_copy_geometry_to_coordinates_single_point(self):
        """Verify _run_fix_copy_geometry_to_coordinates extracts exact original Point coordinates without rounding."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("map_uuid", QVariant.String))
        fields.append(QgsField("sf_longitude", QVariant.Double))
        fields.append(QgsField("sf_latitude", QVariant.Double))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setAttribute("map_uuid", "uuid-test-001")
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(121.05432104, 14.56789012)))
        layer.dataProvider().addFeatures([feat])

        res = self.fix_mod._run_fix_copy_geometry_to_coordinates(layer)
        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 1)

        updated_feat = next(layer.getFeatures())
        self.assertEqual(float(updated_feat["sf_longitude"]), 121.05432104)
        self.assertEqual(float(updated_feat["sf_latitude"]), 14.56789012)

        self.assertIn("uuid-test-001", res["updated_values"])
        self.assertEqual(res["updated_values"]["uuid-test-001"]["sf_longitude"], str(121.05432104))
        self.assertEqual(res["updated_values"]["uuid-test-001"]["sf_latitude"], str(14.56789012))

    def test_copy_geometry_adds_missing_sf_columns(self):
        """Verify sf_longitude and sf_latitude are dynamically added if missing."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("map_uuid", QVariant.String))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setAttribute("map_uuid", "uuid-test-002")
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(120.9876543, 15.1234567)))
        layer.dataProvider().addFeatures([feat])

        res = self.fix_mod._run_fix_copy_geometry_to_coordinates(layer)
        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 1)

        f_names = [f.name().lower() for f in layer.fields()]
        self.assertIn("sf_longitude", f_names)
        self.assertIn("sf_latitude", f_names)

        updated_feat = next(layer.getFeatures())
        self.assertAlmostEqual(float(updated_feat["sf_longitude"]), 120.9876543, places=6)
        self.assertAlmostEqual(float(updated_feat["sf_latitude"]), 15.1234567, places=6)

    def test_copy_geometry_updates_standard_longitude_latitude(self):
        """Verify standard longitude and latitude columns are updated alongside sf_*."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("map_uuid", QVariant.String))
        fields.append(QgsField("longitude", QVariant.Double))
        fields.append(QgsField("latitude", QVariant.Double))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setAttribute("map_uuid", "uuid-test-003")
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(121.5, 14.25)))
        layer.dataProvider().addFeatures([feat])

        res = self.fix_mod._run_fix_copy_geometry_to_coordinates(layer)
        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 1)

        updated_feat = next(layer.getFeatures())
        self.assertAlmostEqual(float(updated_feat["longitude"]), 121.5, places=5)
        self.assertAlmostEqual(float(updated_feat["latitude"]), 14.25, places=5)

    def test_run_fix_dispatcher_routes_copy_geometry(self):
        """Verify run_fix dispatcher routes to copy_geometry_to_coordinates."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("sf_longitude", QVariant.Double))
        fields.append(QgsField("sf_latitude", QVariant.Double))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(122.1111111, 13.2222222)))
        layer.dataProvider().addFeatures([feat])

        res1 = self.fix_mod.run_fix(layer, val_id="copy_geometry_to_coordinates")
        self.assertTrue(res1["success"])
        self.assertEqual(res1["fixed_count"], 1)

        res2 = self.fix_mod.run_fix(layer, val_id="copy_geometry")
        self.assertTrue(res2["success"])

    def test_skip_feature_without_geometry(self):
        """Verify features without geometry are skipped gracefully."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("sf_longitude", QVariant.Double))
        fields.append(QgsField("sf_latitude", QVariant.Double))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        # No geometry set
        layer.dataProvider().addFeatures([feat])

        res = self.fix_mod._run_fix_copy_geometry_to_coordinates(layer)
        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 0)

    def test_targeted_feature_filtering(self):
        """Verify only targeted FIDs or UUIDs are updated when specified."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("map_uuid", QVariant.String))
        fields.append(QgsField("sf_longitude", QVariant.Double))
        fields.append(QgsField("sf_latitude", QVariant.Double))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        f1 = QgsFeature(layer.fields())
        f1.setAttribute("map_uuid", "uuid-target")
        f1.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(121.1, 14.1)))

        f2 = QgsFeature(layer.fields())
        f2.setAttribute("map_uuid", "uuid-other")
        f2.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(122.2, 15.2)))

        layer.dataProvider().addFeatures([f1, f2])

        res = self.fix_mod._run_fix_copy_geometry_to_coordinates(layer, target_uuids=["uuid-target"])
        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 1)
        self.assertIn("uuid-target", res["updated_values"])
        self.assertNotIn("uuid-other", res["updated_values"])

    def test_ui_dropdown_wiring(self):
        """Verify cbmsmv_dialog.py registers the action in combo_actions and delegates to fix handler."""
        with open("references/cbms_mv/cbmsmv_dialog.py", "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn(
            'combo_actions.addItem(copy_geom_ic, "Copy the geometry and paste it into the longitude and latitude columns")',
            content,
        )
        self.assertIn("def _on_copy_geometry_to_coordinates(", content)
        self.assertIn("self._on_copy_geometry_to_coordinates(", content)
        self.assertTrue(hasattr(self.fix_mod, "copy_geometry_to_coordinates"))
        self.assertTrue(hasattr(self.fix_mod, "_run_fix_copy_geometry_to_coordinates"))


if __name__ == "__main__":
    unittest.main()
