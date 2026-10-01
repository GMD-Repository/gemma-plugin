# -*- coding: utf-8 -*-
"""
Unit test for 2027 CBMS Map Validation automated fix:
mv_2027_hp_4b_ea_geocode__missing_fix / cbms_mv_fix
"""

import unittest
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed
from qgis.core import (
    QgsVectorLayer,
    QgsFeature,
    QgsFields,
    QgsField,
)
from qgis.PyQt.QtCore import QVariant

setup_qgis_mock_if_needed()

try:
    from references.cbms_mv.cbms_mv_fix import cbms_mv_fix as fix_module
except ImportError:
    import importlib
    fix_module = importlib.import_module("references.cbms_mv.cbms_mv_fix.cbms_mv_fix")


class TestMv2027Hp4bEaGeocodeMissingFix(unittest.TestCase):
    """Test suite for EA geocode automated fix logic and fallback cascade."""

    def test_priority_1_sf_columns(self):
        """Priority 1: sf_* boundary columns concatenated as-is."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("sf_province_code", QVariant.String))
        fields.append(QgsField("sf_city_mun_code", QVariant.String))
        fields.append(QgsField("sf_barangay_code", QVariant.String))
        fields.append(QgsField("sf_ean", QVariant.String))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setAttribute("sf_province_code", "04")
        feat.setAttribute("sf_city_mun_code", "21")
        feat.setAttribute("sf_barangay_code", "08")
        feat.setAttribute("sf_ean", "002000")
        layer.dataProvider().addFeatures([feat])

        calc = fix_module.compute_ea_geocode_field_calculator(feat, layer)
        self.assertEqual(calc, "042108002000")

    def test_priority_2_standard_columns(self):
        """Priority 2: standard boundary columns concatenated as-is when sf_* missing."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("province_code", QVariant.String))
        fields.append(QgsField("city_mun_code", QVariant.String))
        fields.append(QgsField("barangay_code", QVariant.String))
        fields.append(QgsField("ean", QVariant.String))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setAttribute("province_code", "01")
        feat.setAttribute("city_mun_code", "28")
        feat.setAttribute("barangay_code", "05")
        feat.setAttribute("ean", "001000")
        layer.dataProvider().addFeatures([feat])

        calc = fix_module.compute_ea_geocode_field_calculator(feat, layer)
        self.assertEqual(calc, "012805001000")

    def test_priority_3_sf_bsn_geoid(self):
        """Priority 3: left(sf_bsn_geoid, 14) when boundary components missing."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("sf_bsn_geoid", QVariant.String))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setAttribute("sf_bsn_geoid", "042108002000999999")
        layer.dataProvider().addFeatures([feat])

        calc = fix_module.compute_ea_geocode_field_calculator(feat, layer)
        self.assertEqual(calc, "04210800200099")

    def test_priority_4_bsn_geoid(self):
        """Priority 4: left(bsn_geoid, 14) fallback."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_pts", "memory")
        fields = QgsFields()
        fields.append(QgsField("bsn_geoid", QVariant.String))
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        feat = QgsFeature(layer.fields())
        feat.setAttribute("bsn_geoid", "042108002000888888")
        layer.dataProvider().addFeatures([feat])

        calc = fix_module.compute_ea_geocode_field_calculator(feat, layer)
        self.assertEqual(calc, "04210800200088")


if __name__ == "__main__":
    unittest.main()
