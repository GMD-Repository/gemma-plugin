# -*- coding: utf-8 -*-
"""
Unit test module for CBMS MV Fix: List of geotagged points with missing or NULL bsn_geoid.
Verifies:
- Scenario 1: Concatenate ea_geocode + bsn (or sf_ea_geocode + sf_bsn)
- Scenario 2: Concatenate province_code, city_mun_code, barangay_code, ean, bsn
  (or sf_province_code, sf_city_mun_code, sf_barangay_code, sf_ean, sf_bsn)
- BSN zero-padding to ensure 19-character length
- _run_fix_bsn_geoid feature updates and return structure
- run_fix dispatcher routing
- UI action registration and method delegation
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsFields,
    QgsField,
)
from qgis.PyQt.QtCore import QVariant

setup_qgis_mock_if_needed()


class TestCbmsMvBsnGeoidFix(unittest.TestCase):
    """Test suite for CBMS MV bsn_geoid concatenation fix process."""

    def setUp(self):
        self.fix_mod = importlib.import_module("references.cbms_mv.cbms_mv_fix.cbms_mv_fix")
        self.dialog_mod = importlib.import_module("references.cbms_mv.cbmsmv_dialog")

    def test_scenario_1_sf_ea_geocode_and_sf_bsn(self):
        """1st scenario: sf_ea_geocode + sf_bsn."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("sf_ea_geocode", QVariant.String))
        fields.append(QgsField("sf_bsn", QVariant.String))
        fields.append(QgsField("sf_bsn_geoid", QVariant.String))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setAttribute("sf_ea_geocode", "01280100100001")
        feat.setAttribute("sf_bsn", "00015")
        feat.setAttribute("sf_bsn_geoid", None)
        layer.dataProvider().addFeatures([feat])

        calc = self.fix_mod.compute_bsn_geoid_field_calculator(feat, layer)
        self.assertEqual(calc, "0128010010000100015")
        self.assertEqual(len(calc), 19)

    def test_scenario_1_ea_geocode_and_bsn(self):
        """1st scenario: standard ea_geocode + bsn."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("ea_geocode", QVariant.String))
        fields.append(QgsField("bsn", QVariant.String))
        fields.append(QgsField("bsn_geoid", QVariant.String))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setAttribute("ea_geocode", "02310200500002")
        feat.setAttribute("bsn", "00120")
        layer.dataProvider().addFeatures([feat])

        calc = self.fix_mod.compute_bsn_geoid_field_calculator(feat, layer)
        self.assertEqual(calc, "0231020050000200120")
        self.assertEqual(len(calc), 19)

    def test_scenario_1_bsn_zero_padding(self):
        """1st scenario: short numeric bsn is zero-padded to 5 digits."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("sf_ea_geocode", QVariant.String))
        fields.append(QgsField("sf_bsn", QVariant.String))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setAttribute("sf_ea_geocode", "01280100100001")
        feat.setAttribute("sf_bsn", "1")
        layer.dataProvider().addFeatures([feat])

        calc = self.fix_mod.compute_bsn_geoid_field_calculator(feat, layer)
        self.assertEqual(calc, "0128010010000100001")
        self.assertEqual(len(calc), 19)

    def test_scenario_2_sf_boundary_columns(self):
        """2nd scenario: sf_province_code, sf_city_mun_code, sf_barangay_code, sf_ean, sf_bsn."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("sf_province_code", QVariant.String))
        fields.append(QgsField("sf_city_mun_code", QVariant.String))
        fields.append(QgsField("sf_barangay_code", QVariant.String))
        fields.append(QgsField("sf_ean", QVariant.String))
        fields.append(QgsField("sf_bsn", QVariant.String))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setAttribute("sf_province_code", "0421")
        feat.setAttribute("sf_city_mun_code", "08")
        feat.setAttribute("sf_barangay_code", "002")
        feat.setAttribute("sf_ean", "00050")
        feat.setAttribute("sf_bsn", "00042")
        layer.dataProvider().addFeatures([feat])

        calc = self.fix_mod.compute_bsn_geoid_field_calculator(feat, layer)
        self.assertEqual(calc, "0421080020005000042")
        self.assertEqual(len(calc), 19)

    def test_scenario_2_standard_boundary_columns(self):
        """2nd scenario: province_code, city_mun_code, barangay_code, ean, bsn."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("province_code", QVariant.String))
        fields.append(QgsField("city_mun_code", QVariant.String))
        fields.append(QgsField("barangay_code", QVariant.String))
        fields.append(QgsField("ean", QVariant.String))
        fields.append(QgsField("bsn", QVariant.String))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setAttribute("province_code", "0421")
        feat.setAttribute("city_mun_code", "08")
        feat.setAttribute("barangay_code", "002")
        feat.setAttribute("ean", "00050")
        feat.setAttribute("bsn", "7")
        layer.dataProvider().addFeatures([feat])

        calc = self.fix_mod.compute_bsn_geoid_field_calculator(feat, layer)
        self.assertEqual(calc, "0421080020005000007")
        self.assertEqual(len(calc), 19)

    def test_run_fix_bsn_geoid_layer_update(self):
        """Verify _run_fix_bsn_geoid updates main_layer features and creates updated_values payload."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("map_uuid", QVariant.String))
        fields.append(QgsField("sf_ea_geocode", QVariant.String))
        fields.append(QgsField("sf_bsn", QVariant.String))
        fields.append(QgsField("sf_bsn_geoid", QVariant.String))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setAttribute("map_uuid", "uuid-test-12345")
        feat.setAttribute("sf_ea_geocode", "01280100100001")
        feat.setAttribute("sf_bsn", "00001")
        feat.setAttribute("sf_bsn_geoid", "")
        layer.dataProvider().addFeatures([feat])

        res = self.fix_mod._run_fix_bsn_geoid(layer)
        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 1)

        # Check that layer feature was updated
        updated_feat = next(layer.getFeatures())
        self.assertEqual(updated_feat["sf_bsn_geoid"], "0128010010000100001")
        self.assertIn("uuid-test-12345", res["updated_values"])
        self.assertEqual(
            res["updated_values"]["uuid-test-12345"]["sf_bsn_geoid"],
            "0128010010000100001"
        )

    def test_run_fix_dispatcher_routes_bsn_geoid(self):
        """Verify run_fix routes to bsn_geoid fix for both invalid and missing rule IDs."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("sf_ea_geocode", QVariant.String))
        fields.append(QgsField("sf_bsn", QVariant.String))
        fields.append(QgsField("sf_bsn_geoid", QVariant.String))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setAttribute("sf_ea_geocode", "01280100100001")
        feat.setAttribute("sf_bsn", "00009")
        layer.dataProvider().addFeatures([feat])

        # Test with invalid rule ID
        res1 = self.fix_mod.run_fix(layer, val_id="mv_2027_hp_4b_bsn_geoid__invalid")
        self.assertTrue(res1["success"])
        self.assertEqual(res1["fixed_count"], 1)

        # Test with missing rule ID
        res2 = self.fix_mod.run_fix(layer, val_id="mv_2027_hp_4b_bsn_geoid__missing")
        self.assertTrue(res2["success"])

    def test_ui_dropdown_wiring(self):
        """Verify cbmsmv_dialog.py has Concatenate the bsn_geoid in combo_actions and _on_concatenate_bsn_geoid method."""
        with open("references/cbms_mv/cbmsmv_dialog.py", "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('combo_actions.addItem(concat_bsn_ic, "Concatenate the bsn_geoid")', content)
        self.assertIn("def _on_concatenate_bsn_geoid(", content)
        self.assertIn("self._on_concatenate_bsn_geoid(", content)
        self.assertTrue(hasattr(self.fix_mod, "concatenate_bsn_geoid"))

    def test_concatenate_bsn_geoid_single_selection_scoping_with_target_fids(self):
        """Verify executing fix with 1 target FID strictly updates only that feature."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("map_uuid", QVariant.String))
        fields.append(QgsField("sf_ea_geocode", QVariant.String))
        fields.append(QgsField("sf_bsn", QVariant.String))
        fields.append(QgsField("sf_bsn_geoid", QVariant.String))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        f1 = QgsFeature(layer.fields())
        f1.setAttribute("map_uuid", "uuid-1")
        f1.setAttribute("sf_ea_geocode", "01280100100001")
        f1.setAttribute("sf_bsn", "00001")
        f1.setAttribute("sf_bsn_geoid", None)

        f2 = QgsFeature(layer.fields())
        f2.setAttribute("map_uuid", "uuid-2")
        f2.setAttribute("sf_ea_geocode", "01280100100002")
        f2.setAttribute("sf_bsn", "00002")
        f2.setAttribute("sf_bsn_geoid", None)

        f3 = QgsFeature(layer.fields())
        f3.setAttribute("map_uuid", "uuid-3")
        f3.setAttribute("sf_ea_geocode", "01280100100003")
        f3.setAttribute("sf_bsn", "00003")
        f3.setAttribute("sf_bsn_geoid", None)

        layer.dataProvider().addFeatures([f1, f2, f3])
        all_feats = list(layer.getFeatures())
        f1_id, f2_id, f3_id = all_feats[0].id(), all_feats[1].id(), all_feats[2].id()

        # Fix strictly for feature 2
        res = self.fix_mod._run_fix_bsn_geoid(layer, target_fids=[f2_id])
        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 1)

        refreshed = {feat.id(): feat for feat in layer.getFeatures()}
        # Only f2 should have updated sf_bsn_geoid
        self.assertEqual(refreshed[f2_id]["sf_bsn_geoid"], "0128010010000200002")
        # f1 and f3 must remain untouched (None or empty)
        self.assertTrue(not refreshed[f1_id]["sf_bsn_geoid"])
        self.assertTrue(not refreshed[f3_id]["sf_bsn_geoid"])

    def test_concatenate_bsn_geoid_single_selection_scoping_with_table_checked(self):
        """Verify executing fix with UI table strictly processes checked row only."""
        from qgis.PyQt.QtWidgets import QTableWidget, QTableWidgetItem
        from qgis.PyQt.QtCore import Qt

        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("map_uuid", QVariant.String))
        fields.append(QgsField("sf_ea_geocode", QVariant.String))
        fields.append(QgsField("sf_bsn", QVariant.String))
        fields.append(QgsField("sf_bsn_geoid", QVariant.String))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        f1 = QgsFeature(layer.fields())
        f1.setAttribute("map_uuid", "uuid-1")
        f1.setAttribute("sf_ea_geocode", "01280100100001")
        f1.setAttribute("sf_bsn", "00001")

        f2 = QgsFeature(layer.fields())
        f2.setAttribute("map_uuid", "uuid-2")
        f2.setAttribute("sf_ea_geocode", "01280100100002")
        f2.setAttribute("sf_bsn", "00002")

        f3 = QgsFeature(layer.fields())
        f3.setAttribute("map_uuid", "uuid-3")
        f3.setAttribute("sf_ea_geocode", "01280100100003")
        f3.setAttribute("sf_bsn", "00003")

        layer.dataProvider().addFeatures([f1, f2, f3])
        all_feats = list(layer.getFeatures())
        f1_id, f2_id, f3_id = all_feats[0].id(), all_feats[1].id(), all_feats[2].id()

        table = QTableWidget(3, 4)
        for r, (fid, uuid_val, ean, bsn) in enumerate([
            (f1_id, "uuid-1", "01280100100001", "00001"),
            (f2_id, "uuid-2", "01280100100002", "00002"),
            (f3_id, "uuid-3", "01280100100003", "00003"),
        ]):
            item0 = QTableWidgetItem(f"Row {r}")
            item0.setData(Qt.UserRole, fid)
            item0.setData(Qt.UserRole + 1, uuid_val)
            item0.setData(Qt.UserRole + 6, fid)
            item0.setData(Qt.UserRole + 7, uuid_val)
            # Only row 1 is checked!
            item0.setCheckState(Qt.Checked if r == 1 else Qt.Unchecked)
            table.setItem(r, 0, item0)

        # Run fix passing table and target_rows=[1]
        res = self.fix_mod._run_fix_bsn_geoid(layer, table=table, target_rows=[1])
        self.assertTrue(res["success"])
        self.assertEqual(res["fixed_count"], 1)

        refreshed = {feat.id(): feat for feat in layer.getFeatures()}
        self.assertEqual(refreshed[f2_id]["sf_bsn_geoid"], "0128010010000200002")
        self.assertTrue(not refreshed[f1_id]["sf_bsn_geoid"])
        self.assertTrue(not refreshed[f3_id]["sf_bsn_geoid"])

    def test_concatenate_bsn_geoid_empty_selection_warns_and_does_nothing(self):
        """Verify executing fix with no checked rows or selection returns early and modifies nothing."""
        from qgis.PyQt.QtWidgets import QTableWidget, QTableWidgetItem
        from qgis.PyQt.QtCore import Qt

        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("map_uuid", QVariant.String))
        fields.append(QgsField("sf_ea_geocode", QVariant.String))
        fields.append(QgsField("sf_bsn", QVariant.String))
        fields.append(QgsField("sf_bsn_geoid", QVariant.String))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        f1 = QgsFeature(layer.fields())
        f1.setAttribute("map_uuid", "uuid-1")
        f1.setAttribute("sf_ea_geocode", "01280100100001")
        f1.setAttribute("sf_bsn", "00001")
        layer.dataProvider().addFeatures([f1])

        table = QTableWidget(1, 4)
        item0 = QTableWidgetItem("Row 0")
        item0.setCheckState(Qt.Unchecked)
        table.setItem(0, 0, item0)

        res = self.fix_mod._run_fix_bsn_geoid(layer, table=table, target_rows=[])
        self.assertFalse(res["success"])
        self.assertEqual(res["fixed_count"], 0)
        self.assertIn("select at least one row", res.get("message", "").lower())

        refreshed = list(layer.getFeatures())
        self.assertTrue(not refreshed[0]["sf_bsn_geoid"])


if __name__ == "__main__":
    unittest.main()
