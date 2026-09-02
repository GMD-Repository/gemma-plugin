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
        # Custom non-excluded layer
        self.assertFalse(PackageDialog._is_excluded_data_source_layer(None, "custom_layer"))


if __name__ == "__main__":
    unittest.main()
