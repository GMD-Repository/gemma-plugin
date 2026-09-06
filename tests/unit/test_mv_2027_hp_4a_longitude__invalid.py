# -*- coding: utf-8 -*-
"""
Unit test module for mv_2027_hp_4a_longitude__invalid.py
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, QgsProcessingContext, QgsProcessingFeedback
from qgis.core import QgsGeometry, QgsPointXY, QgsVectorLayer, QgsFeature, QgsFields, QgsField, QVariant

setup_qgis_mock_if_needed()


class TestMv2027Hp4aLongitudeInvalid(unittest.TestCase):
    """Test suite for mv_2027_hp_4a_longitude__invalid.py."""

    def setUp(self):
        self.gmdhelpers = importlib.import_module("gmd_scripts.gmdhelpers")
        self.mod = importlib.import_module("gmd_scripts.cbms_mv.mv_2027_hp_4a_longitude__invalid")
        self.alg_cls = getattr(self.mod, "mv_2027_hp_4a_longitude__invalid")
        self.alg = self.alg_cls()

    def test_algorithm_metadata(self):
        """Verify algorithm metadata return values."""
        self.assertEqual(self.alg.name(), "mv_2027_hp_4a_longitude__invalid")
        self.assertEqual(self.alg.displayName(), "mv_2027_hp_4a_longitude__invalid")
        self.assertEqual(self.alg.group(), "2027 CBMS")
        self.assertEqual(self.alg.groupId(), "cbms_mv")

    def test_module_import_and_instantiation(self):
        """Verify algorithm instantiation and createInstance."""
        self.assertIsNotNone(self.alg)
        inst = self.alg.createInstance()
        self.assertIsInstance(inst, self.alg_cls)


if __name__ == "__main__":
    unittest.main()
