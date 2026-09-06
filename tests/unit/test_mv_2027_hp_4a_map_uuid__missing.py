# -*- coding: utf-8 -*-
"""
Unit test module for mv_2027_hp_4a_map_uuid__missing.py (gmd_scripts/cbms_mv/mv_2027_hp_4a_map_uuid__missing.py).
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, QgsProcessingContext, QgsProcessingFeedback
from qgis.core import QgsGeometry, QgsPointXY, QgsVectorLayer, QgsFeature, QgsFields, QgsField, QVariant

setup_qgis_mock_if_needed()


class TestMv2027Hp4aMapUuidMissing(unittest.TestCase):
    """Test suite for mv_2027_hp_4a_map_uuid__missing.py."""

    def setUp(self):
        self.gmdhelpers = importlib.import_module("gmd_scripts.gmdhelpers")
        if not hasattr(self.gmdhelpers, "select_mv"):
            self.gmdhelpers.select_mv = lambda layer, extra_fields, context=None, feedback=None: layer
        self.mod = importlib.import_module("gmd_scripts.cbms_mv.mv_2027_hp_4a_map_uuid__missing")
        self.alg_cls = getattr(self.mod, "mv_2027_hp_4a_map_uuid__missing")
        self.alg = self.alg_cls()

    def test_algorithm_metadata(self):
        """Verify algorithm metadata return values."""
        self.assertEqual(self.alg.name(), "mv_2027_hp_4a_map_uuid__missing")
        self.assertEqual(self.alg.displayName(), "mv_2027_hp_4a_map_uuid__missing")
        self.assertEqual(self.alg.group(), "2027 CBMS")
        self.assertEqual(self.alg.groupId(), "cbms_mv")
        self.assertIn("List of geotagged points without CBMS Form 2 datafile.", self.alg.shortHelpString())

    def test_module_import_and_instantiation(self):
        """Verify algorithm instantiation and createInstance."""
        self.assertIsNotNone(self.alg)
        inst = self.alg.createInstance()
        self.assertIsInstance(inst, self.alg_cls)

    def test_algorithm_parameters(self):
        """Verify algorithm registers required input and output parameters."""
        self.alg.initAlgorithm()
        param_names = [p.name() for p in self.alg.parameterDefinitions()]
        self.assertIn("INPUT_DATA", param_names)
        self.assertIn("INPUT_LAYER", param_names)
        self.assertIn("OUTPUT", param_names)

    def test_process_algorithm_execution_without_reference_layer(self):
        """Verify that when no reference JSON layer is provided, it only flags missing map_uuid in GeoJSON."""
        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_points", "memory")
        fields = QgsFields()
        fields.append(QgsField("map_uuid", QVariant.String))
        fields.append(QgsField("bsn_geoid", QVariant.String))
        fields.append(QgsField("bsn", QVariant.String))
        layer.setFields(fields)

        # Feature 1: Valid map_uuid
        f1 = QgsFeature(fields)
        f1.setAttribute("map_uuid", "uuid-1234")
        f1.setAttribute("bsn_geoid", "04210100100000100001")
        f1.setAttribute("bsn", "00001")
        f1.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(121.0, 14.0)))

        # Feature 2: Missing map_uuid
        f2 = QgsFeature(fields)
        f2.setAttribute("map_uuid", None)
        f2.setAttribute("bsn_geoid", "04210100100000100002")
        f2.setAttribute("bsn", "00002")
        f2.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(121.1, 14.1)))

        # Feature 3: BSN 0 (should be skipped)
        f3 = QgsFeature(fields)
        f3.setAttribute("map_uuid", None)
        f3.setAttribute("bsn_geoid", "04210100100000100000")
        f3.setAttribute("bsn", "00000")
        f3.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(121.2, 14.2)))

        layer.setFeatures([f1, f2, f3])

        context = QgsProcessingContext()
        feedback = QgsProcessingFeedback()
        params = {
            "INPUT_LAYER": layer,
            "OUTPUT": "memory:",
        }

        res = self.alg.processAlgorithm(params, context, feedback)
        self.assertIn("OUTPUT", res)

    def test_process_algorithm_execution_with_json_data(self):
        """Verify 19-digit bsn_geoid matching between GeoJSON and JSON components."""
        import tempfile
        import json
        import os

        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_points", "memory")
        fields = QgsFields()
        fields.append(QgsField("map_uuid", QVariant.String))
        fields.append(QgsField("bsn_geoid", QVariant.String))
        fields.append(QgsField("bsn", QVariant.String))
        layer.setFields(fields)

        # 069 (prov: 69) + 07 (mun: 7) + 001 (bgy: 1) + 001000 (ean: 1000) + 00222 (bsn: 222)
        sample_geoid = "0690700100100000222"

        # Feature 1: Matching Form 2 with matching map_uuid
        f1 = QgsFeature(fields)
        f1.setAttribute("map_uuid", "uuid-matching")
        f1.setAttribute("bsn_geoid", sample_geoid)
        f1.setAttribute("bsn", "00222")
        f1.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(120.69, 15.57)))

        # Feature 2: Matching Form 2 but Form 2 is missing map_uuid
        f2 = QgsFeature(fields)
        f2.setAttribute("map_uuid", "uuid-target")
        f2.setAttribute("bsn_geoid", "0690700100100000333")
        f2.setAttribute("bsn", "00333")
        f2.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(120.70, 15.58)))

        layer.setFeatures([f1, f2])

        json_records = [
            {
                "province_code": 69,
                "city_mun_code": 7,
                "barangay_code": 1,
                "ean": 1000,
                "bsn_code": 222,
                "map_uuid": "uuid-matching",
            },
            {
                "province_code": 69,
                "city_mun_code": 7,
                "barangay_code": 1,
                "ean": 1000,
                "bsn_code": 333,
                "map_uuid": None,  # Datafile exists but lacks map_uuid
            },
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
            json.dump(json_records, tf)
            json_file = tf.name

        try:
            context = QgsProcessingContext()
            feedback = QgsProcessingFeedback()
            params = {
                "INPUT_LAYER": layer,
                "INPUT_DATA": json_file,
                "OUTPUT": "memory:",
            }

            res = self.alg.processAlgorithm(params, context, feedback)
            self.assertIn("OUTPUT", res)
        finally:
            if os.path.exists(json_file):
                os.remove(json_file)


if __name__ == "__main__":
    unittest.main()
