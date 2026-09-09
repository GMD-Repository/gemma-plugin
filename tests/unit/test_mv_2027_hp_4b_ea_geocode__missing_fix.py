# -*- coding: utf-8 -*-
"""
Unit test module for mv_2027_hp_4b_ea_geocode__missing_fix.py.
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, QgsProcessingFeedback
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsFields,
    QgsField,
    QVariant,
    QgsGeometry,
    QgsPointXY,
)

setup_qgis_mock_if_needed()


class TestMv2027Hp4bEaGeocodeMissingFix(unittest.TestCase):
    """Test suite for automated EA geocode concatenation fix module."""

    def setUp(self):
        self.fix_mod = importlib.import_module(
            "references.cbms_mv.cbms_mv_fix.mv_2027_hp_4b_ea_geocode__missing_fix"
        )
        self.registry_mod = importlib.import_module("references.cbms_mv.cbms_mv_fix")

    def _create_sample_layer(self):
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_building_points", "memory")
        fields = QgsFields()
        fields.append(QgsField("fid", QVariant.Int))
        fields.append(QgsField("sf_map_uuid", QVariant.String))
        fields.append(QgsField("sf_bsn_geoid", QVariant.String))
        fields.append(QgsField("sf_ea_geocode", QVariant.String))
        fields.append(QgsField("sf_region_code", QVariant.String))
        fields.append(QgsField("sf_province_code", QVariant.String))
        fields.append(QgsField("sf_city_mun_code", QVariant.String))
        fields.append(QgsField("sf_barangay_code", QVariant.String))
        fields.append(QgsField("sf_ean", QVariant.String))
        fields.append(QgsField("sf_bsn", QVariant.String))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        # Row 1: Already has geocode
        f1 = QgsFeature(layer.fields())
        f1.setAttribute("fid", 1)
        f1.setAttribute("sf_map_uuid", "uuid-1111")
        f1.setAttribute("sf_bsn_geoid", "02108002001000")
        f1.setAttribute("sf_ea_geocode", "0402108002001000")
        f1.setAttribute("sf_region_code", "04")
        f1.setAttribute("sf_province_code", "021")
        f1.setAttribute("sf_city_mun_code", "08")
        f1.setAttribute("sf_barangay_code", "002")
        f1.setAttribute("sf_ean", "001000")
        f1.setAttribute("sf_bsn", "02105")
        f1.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(121.0, 14.0)))

        # Row 2: Missing geocode (Row 2 in user image)
        f2 = QgsFeature(layer.fields())
        f2.setAttribute("fid", 2)
        f2.setAttribute("sf_map_uuid", "0231214c-23a5-48b6-98ec-77f6b9cda44b")
        f2.setAttribute("sf_bsn_geoid", "")
        f2.setAttribute("sf_ea_geocode", None)
        f2.setAttribute("sf_region_code", "04")
        f2.setAttribute("sf_province_code", "021")
        f2.setAttribute("sf_city_mun_code", "08")
        f2.setAttribute("sf_barangay_code", "002")
        f2.setAttribute("sf_ean", "001000")
        f2.setAttribute("sf_bsn", "02104")
        f2.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(121.1, 14.1)))

        # Row 3: Missing geocode (Row 3 in user image)
        f3 = QgsFeature(layer.fields())
        f3.setAttribute("fid", 3)
        f3.setAttribute("sf_map_uuid", "10a7a3f5-3ce3-448c-a33f-e53c98ee7c77")
        f3.setAttribute("sf_bsn_geoid", "02108002001000")
        f3.setAttribute("sf_ea_geocode", None)
        f3.setAttribute("sf_region_code", "04")
        f3.setAttribute("sf_province_code", "021")
        f3.setAttribute("sf_city_mun_code", "08")
        f3.setAttribute("sf_barangay_code", "002")
        f3.setAttribute("sf_ean", "001000")
        f3.setAttribute("sf_bsn", "60001")
        f3.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(121.2, 14.2)))

        layer.dataProvider().addFeatures([f1, f2, f3])
        return layer

    def test_compute_ea_geocode_field_calculator(self):
        """Verify field calculator formula accurately concatenates codes."""
        layer = self._create_sample_layer()
        features = list(layer.getFeatures())
        f2 = features[1]

        res = self.fix_mod.compute_ea_geocode_field_calculator(f2, layer)
        self.assertEqual(res, "02108002001000")

    def test_compute_ea_geocode_with_strict_3_digit_province(self):
        """Verify province_code is strictly zero-padded to 3 digits."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pad", "memory")
        fields = QgsFields()
        fields.append(QgsField("province_code", QVariant.Int))
        fields.append(QgsField("city_mun_code", QVariant.Int))
        fields.append(QgsField("barangay_code", QVariant.Int))
        fields.append(QgsField("ean", QVariant.Int))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setAttribute("province_code", 21)  # 21 -> strictly '021'
        feat.setAttribute("city_mun_code", 8)   # 8 -> '08'
        feat.setAttribute("barangay_code", 2)   # 2 -> '002'
        feat.setAttribute("ean", 1000)          # 1000 -> '001000'
        layer.dataProvider().addFeatures([feat])

        res = self.fix_mod.compute_ea_geocode_field_calculator(feat, layer)
        self.assertEqual(res, "02108002001000")

    def test_run_fix_single_target_fid(self):
        """Verify clicking Fix button on single row (target_fids) updates only that feature."""
        layer = self._create_sample_layer()
        target_fids = [2]
        feedback = QgsProcessingFeedback()

        res = self.fix_mod.run_fix(layer, target_fids=target_fids, feedback=feedback)

        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("fixed_count"), 1)
        updated = res.get("updated_values", {})
        self.assertIn(2, updated)
        self.assertEqual(updated[2]["sf_ea_geocode"], "02108002001000")

        # Verify only target layer feature attribute updated, others remain untouched
        feat2 = layer.getFeature(2)
        feat3 = layer.getFeature(3)
        self.assertEqual(feat2["sf_ea_geocode"], "02108002001000")
        self.assertIsNone(feat3["sf_ea_geocode"])

    def test_run_fix_by_target_uuid(self):
        """Verify fixing row by UUID works correctly."""
        layer = self._create_sample_layer()
        target_uuids = ["0231214c-23a5-48b6-98ec-77f6b9cda44b"]
        feedback = QgsProcessingFeedback()

        res = self.fix_mod.run_fix(layer, target_uuids=target_uuids, feedback=feedback)

        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("fixed_count"), 1)
        updated = res.get("updated_values", {})
        self.assertIn("0231214c-23a5-48b6-98ec-77f6b9cda44b", updated)
        self.assertEqual(
            updated["0231214c-23a5-48b6-98ec-77f6b9cda44b"]["sf_ea_geocode"],
            "02108002001000",
        )

    def test_run_fix_batch_selection(self):
        """Verify fixing multiple checked rows (Fix Selected)."""
        layer = self._create_sample_layer()
        target_fids = [2, 3]
        feedback = QgsProcessingFeedback()

        res = self.fix_mod.run_fix(layer, target_fids=target_fids, feedback=feedback)

        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("fixed_count"), 2)

        feat2 = layer.getFeature(2)
        feat3 = layer.getFeature(3)
        self.assertEqual(feat2["sf_ea_geocode"], "02108002001000")
        self.assertEqual(feat3["sf_ea_geocode"], "02108002001000")

    def test_registry_discovery(self):
        """Verify module registry discovery for mv_2027_hp_4b_ea_geocode__missing."""
        self.assertTrue(self.registry_mod.has_fix("mv_2027_hp_4b_ea_geocode__missing"))
        h1 = self.registry_mod.get_fix_handler("mv_2027_hp_4b_ea_geocode__missing")
        self.assertIsNotNone(h1)

    def test_run_fix_unhashable_dict_handling(self):
        """Verify passing dictionary or unhashable structures in target_fids does not raise TypeError."""
        layer = self._create_sample_layer()
        target_fids = [{"fid": 2, "uuid": "0231214c-23a5-48b6-98ec-77f6b9cda44b"}]
        feedback = QgsProcessingFeedback()

        res = self.fix_mod.run_fix(layer, target_fids=target_fids, feedback=feedback)
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("fixed_count"), 1)

    def test_run_fix_feature_with_dict_attribute(self):
        """Verify layer features containing dictionary or unhashable attributes execute cleanly."""
        layer = self._create_sample_layer()
        # Set a dict attribute on feature 2
        feat = layer.getFeature(2)
        feat.setAttribute("sf_fid", {"nested": "dict_id", "fid": 2})

        feedback = QgsProcessingFeedback()
        res = self.fix_mod.run_fix(layer, target_fids=[2], feedback=feedback)
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("fixed_count"), 1)


if __name__ == "__main__":
    unittest.main()
