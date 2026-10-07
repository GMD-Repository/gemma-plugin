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


if __name__ == "__main__":
    unittest.main()
