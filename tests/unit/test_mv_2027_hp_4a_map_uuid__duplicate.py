# -*- coding: utf-8 -*-
"""
Unit test module for mv_2027_hp_4a_map_uuid__duplicate.py (gmd_scripts/cbms_mv/mv_2027_hp_4a_map_uuid__duplicate.py).
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, QgsProcessingContext, QgsProcessingFeedback
from tests.mocks.sample_data import create_sample_point_layer
from qgis.core import QgsGeometry, QgsPointXY

setup_qgis_mock_if_needed()


class TestMv2027Hp4aMapUuidDuplicate(unittest.TestCase):
    """Test suite for mv_2027_hp_4a_map_uuid__duplicate.py."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.cbms_mv.mv_2027_hp_4a_map_uuid__duplicate")
        self.alg_cls = self.mod.Mv2027Hp4aMapUuidDuplicateAlgorithm
        self.alg = self.alg_cls()

    def test_algorithm_metadata(self):
        """Verify algorithm metadata return values match strict requirements."""
        self.assertEqual(self.alg.name(), "mv_2027_hp_4a_map_uuid__duplicate")
        self.assertEqual(self.alg.displayName(), "mv_2027_hp_4a_map_uuid__duplicate")
        self.assertEqual(self.alg.group(), "2027 CBMS")
        self.assertEqual(self.alg.groupId(), "cbms_mv")
        self.assertIn("List of geotagged points with duplicate map_uuid.", self.alg.shortHelpString())

    def test_module_import_and_instantiation(self):
        """Verify algorithm instantiation and instance creation."""
        self.assertIsNotNone(self.alg)
        inst = self.alg.createInstance()
        self.assertIsInstance(inst, self.alg_cls)

    def test_check_geometry_validity(self):
        """Test validity checking helper function."""
        check_validity = self.mod.check_geometry_validity
        valid_geom = QgsGeometry.fromPointXY(QgsPointXY(121.0, 14.0))
        self.assertTrue(check_validity(valid_geom))

        empty_geom = QgsGeometry()
        self.assertFalse(check_validity(empty_geom))
        self.assertFalse(check_validity(None))

    def test_algorithm_parameters(self):
        """Verify algorithm registers required input and output parameters."""
        self.alg.initAlgorithm()
        param_names = [p.name() for p in self.alg.parameterDefinitions()]
        self.assertIn("INPUT_DATA", param_names)
        self.assertIn("INPUT_LAYER", param_names)
        self.assertIn("OUTPUT", param_names)

    def test_process_algorithm_execution(self):
        """Test processAlgorithm logic on vector layer with duplicate map_uuid attributes."""
        from qgis.core import QgsVectorLayer, QgsFeature, QgsFields, QgsField, QVariant

        layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_points", "memory")
        fields = QgsFields()
        fields.append(QgsField("map_uuid", QVariant.String))
        fields.append(QgsField("name", QVariant.String))
        layer.setFields(fields)

        feat1 = QgsFeature(fields)
        feat1.setAttribute("map_uuid", "uuid_101")
        feat1.setAttribute("name", "Point A")
        feat1.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(121.0, 14.0)))

        feat2 = QgsFeature(fields)
        feat2.setAttribute("map_uuid", "uuid_101")  # Duplicate map_uuid
        feat2.setAttribute("name", "Point B")
        feat2.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(121.1, 14.1)))

        feat3 = QgsFeature(fields)
        feat3.setAttribute("map_uuid", "uuid_202")  # Unique map_uuid
        feat3.setAttribute("name", "Point C")
        feat3.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(121.2, 14.2)))

        layer.setFeatures([feat1, feat2, feat3])

        context = QgsProcessingContext()
        feedback = QgsProcessingFeedback()

        params = {
            "INPUT_LAYER": layer,
            "OUTPUT": "memory:",
        }

        res = self.alg.processAlgorithm(params, context, feedback)
        self.assertIn("OUTPUT", res)


if __name__ == "__main__":
    unittest.main()
