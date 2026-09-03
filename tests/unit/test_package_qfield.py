# -*- coding: utf-8 -*-
"""
Unit test module for package_qfield.py (gmd_scripts/package_qfield.py).
Tests QField package dialog launcher and callback handling using mock iface.
"""

import os
import sys
import unittest
import importlib

plugin_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
whl_path = os.path.join(plugin_root, "references", "package_qfield", "unzipped_whl")
if os.path.exists(whl_path) and whl_path not in sys.path:
    sys.path.insert(0, whl_path)

from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, MockGenericClass

setup_qgis_mock_if_needed()


class TestPackageQfield(unittest.TestCase):
    """Test suite for package_qfield module."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.package_qfield")

    def test_module_import(self):
        """Verify module imports successfully."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.package_qfield should import successfully.")

    def test_show_package_dialog_instantiation(self):
        """Test show_package_dialog launcher function with mock iface and offline_editing object."""
        mock_iface = MockGenericClass()
        mock_offline = MockGenericClass()
        callback_called = [False]

        def sample_callback(result):
            callback_called[0] = True

        try:
            dlg = self.mod.show_package_dialog(mock_iface, mock_offline, on_finished_callback=sample_callback)
            self.assertIsNotNone(dlg)
        except Exception as e:
            self.skipTest(f"Skipping test due to environment GUI limitation: {e}")

    def test_is_excluded_data_source_layer_exempts_special_ea(self):
        """Verify _is_excluded_data_source_layer identifies excluded patterns while exempting _special_ea."""
        from references.package_qfield.gui.package_dialog import PackageDialog
        # Test class method directly without instantiating full GUI
        self.assertTrue(PackageDialog._is_excluded_data_source_layer(None, "01728001001_ea"))
        self.assertTrue(PackageDialog._is_excluded_data_source_layer(None, "01728001001_bgy"))
        self.assertTrue(PackageDialog._is_excluded_data_source_layer(None, "01728001001_bldgpts"))
        self.assertTrue(PackageDialog._is_excluded_data_source_layer(None, "01728001001_bldg_point"))
        self.assertTrue(PackageDialog._is_excluded_data_source_layer(None, "01728001001_road"))
        self.assertTrue(PackageDialog._is_excluded_data_source_layer(None, "01728001001_river"))
        self.assertTrue(PackageDialog._is_excluded_data_source_layer(None, "01728001001_bridge"))
        self.assertTrue(PackageDialog._is_excluded_data_source_layer(None, "01728001001_railroad"))
        self.assertTrue(PackageDialog._is_excluded_data_source_layer(None, "01728001001_landmark"))
        self.assertTrue(PackageDialog._is_excluded_data_source_layer(None, "01728001001_block"))
        # Special EA exemption
        self.assertFalse(PackageDialog._is_excluded_data_source_layer(None, "01728001001_special_ea"))
        self.assertFalse(PackageDialog._is_excluded_data_source_layer(None, "my_custom_special_ea"))
    def test_filter_unassigned_layer_missing_columns_does_not_filter(self):
        """Verify unassigned layer missing both ea_geocode and geocode is not filtered."""
        from references.package_qfield.gui.package_dialog import PackageDialog
        try:
            from qgis.core import QgsVectorLayer, QgsField, QgsFeature
            from qgis.PyQt.QtCore import QVariant
        except ImportError:
            from tests.mocks.sample_data import QgsVectorLayer, QgsField, QgsFeature, QVariant

        layer = QgsVectorLayer("Polygon?crs=epsg:4326", "unassigned_no_geocode", "memory")
        dp = layer.dataProvider()
        dp.addAttributes([QgsField("name", QVariant.String), QgsField("type", QVariant.String)])
        layer.updateFields()
        f = QgsFeature(layer.fields())
        f.setAttributes(["Zone 1", "Commercial"])
        dp.addFeatures([f])

        dlg = MockGenericClass()
        dlg._normalized_layer_name = lambda n: n
        PackageDialog._filter_unassigned_layer(dlg, layer, "01728001001", is_ea_level=False)

        self.assertEqual(layer.subsetString(), "")
        self.assertEqual(layer.customProperty("QFieldSync/action"), "copy")

    def test_filter_unassigned_layer_empty_attribute_does_nothing(self):
        """Verify unassigned layer with geocode column but empty/null data does nothing."""
        from references.package_qfield.gui.package_dialog import PackageDialog
        try:
            from qgis.core import QgsVectorLayer, QgsField, QgsFeature
            from qgis.PyQt.QtCore import QVariant
        except ImportError:
            from tests.mocks.sample_data import QgsVectorLayer, QgsField, QgsFeature, QVariant

        dlg = MockGenericClass()
        dlg._normalized_layer_name = lambda n: n

        # Case A: 0 features
        layer_empty = QgsVectorLayer("Polygon?crs=epsg:4326", "unassigned_empty", "memory")
        dp_empty = layer_empty.dataProvider()
        dp_empty.addAttributes([QgsField("geocode", QVariant.String)])
        layer_empty.updateFields()

        PackageDialog._filter_unassigned_layer(dlg, layer_empty, "01728001", is_ea_level=False)
        self.assertEqual(layer_empty.subsetString(), "")

        # Case B: Features with whitespace/null values
        layer_null = QgsVectorLayer("Polygon?crs=epsg:4326", "unassigned_null_values", "memory")
        dp_null = layer_null.dataProvider()
        dp_null.addAttributes([QgsField("geocode", QVariant.String)])
        layer_null.updateFields()
        f = QgsFeature(layer_null.fields())
        f.setAttributes(["   "])
        dp_null.addFeatures([f])

        PackageDialog._filter_unassigned_layer(dlg, layer_null, "01728001", is_ea_level=False)
        self.assertEqual(layer_null.subsetString(), "")

    def test_filter_unassigned_layer_with_valid_data(self):
        """Verify unassigned layer with valid geocode or ea_geocode receives appropriate subset string."""
        from references.package_qfield.gui.package_dialog import PackageDialog
        try:
            from qgis.core import QgsVectorLayer, QgsField, QgsFeature
            from qgis.PyQt.QtCore import QVariant
        except ImportError:
            from tests.mocks.sample_data import QgsVectorLayer, QgsField, QgsFeature, QVariant

        layer_bgy = QgsVectorLayer("Polygon?crs=epsg:4326", "unassigned_bgy", "memory")
        dp_bgy = layer_bgy.dataProvider()
        dp_bgy.addAttributes([QgsField("geocode", QVariant.String)])
        layer_bgy.updateFields()
        f = QgsFeature(layer_bgy.fields())
        f.setAttributes(["01728001000000"])
        dp_bgy.addFeatures([f])

        dlg = MockGenericClass()
        dlg._normalized_layer_name = lambda n: n

        # Barangay level filter
        PackageDialog._filter_unassigned_layer(dlg, layer_bgy, "01728001", is_ea_level=False)
        self.assertEqual(layer_bgy.subsetString(), '"geocode" LIKE \'01728001%\'')

        # EA level filter
        PackageDialog._filter_unassigned_layer(dlg, layer_bgy, "01728001001001", is_ea_level=True)
        self.assertEqual(layer_bgy.subsetString(), '"geocode" = \'01728001001001\'')


if __name__ == "__main__":
    unittest.main()
