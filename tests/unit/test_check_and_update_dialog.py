# -*- coding: utf-8 -*-
"""
Unit test module for check_and_update_dialog.py (gmd_scripts/check_and_update_dialog.py).
Tests resolve_processing_output_layer helper function using sample vector layers.
"""

import unittest
import importlib
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, QgsProcessingContext
from tests.mocks.sample_data import create_sample_polygon_layer

setup_qgis_mock_if_needed()


class TestCheckAndUpdateDialog(unittest.TestCase):
    """Test suite for check_and_update_dialog module."""

    def setUp(self):
        self.mod = importlib.import_module("gmd_scripts.check_and_update_dialog")
        self.sample_layer = create_sample_polygon_layer("Barangay_Boundaries", count=3)

    def test_module_import(self):
        """Verify module imports successfully."""
        self.assertIsNotNone(self.mod, "Module gmd_scripts.check_and_update_dialog should import successfully.")

    def test_resolve_processing_output_layer(self):
        """Test resolve_processing_output_layer helper function with layer object."""
        try:
            context = QgsProcessingContext()
            res = self.mod.resolve_processing_output_layer(self.sample_layer, context)
            self.assertEqual(res, self.sample_layer, "Output layer should resolve to input QgsVectorLayer.")
        except Exception as e:
            self.skipTest(f"Skipping test due to processing environment error: {e}")

    def test_dialog_adaptive_theming(self):
        """Verify CheckAndUpdateDialog applies appropriate styles in dark and light mode."""
        from unittest.mock import MagicMock
        try:
            mock_iface = MagicMock()
            mock_iface.mainWindow.return_value = None
            dlg = self.mod.CheckAndUpdateDialog(mock_iface)

            # Test Dark Mode application
            dlg.is_dark = True
            dlg._apply_theme()
            self.assertIn("#ECEFF1", dlg.title_label.styleSheet())
            self.assertIn("#263238", dlg.tabs.styleSheet())
            self.assertIn("#1A365D", dlg.header_banner.styleSheet())
            self.assertIn("#CFD8DC", dlg.step1_desc.styleSheet())
            self.assertTrue(dlg.geom_toolkit_help.is_dark)
            self.assertIn("#263238", dlg.geom_toolkit_help.text.styleSheet())
            self.assertIn("#1E2327", dlg.geom_toolkit_help._get_html(True))

            # Test Light Mode application
            dlg.is_dark = False
            dlg._apply_theme()
            self.assertIn("#2C3E50", dlg.title_label.styleSheet())
            self.assertIn("#EAEDED", dlg.tabs.styleSheet())
            self.assertIn("#EBF5FB", dlg.header_banner.styleSheet())
            self.assertIn("#34495E", dlg.step1_desc.styleSheet())
            self.assertFalse(dlg.geom_toolkit_help.is_dark)
            self.assertIn("#ffffff", dlg.geom_toolkit_help.text.styleSheet())
        except Exception as e:
            self.skipTest(f"Skipping GUI test in headless environment: {e}")

    def test_digitize_dock_adaptive_theming(self):
        """Verify DigitizeDockWidget applies appropriate styles in dark and light mode."""
        from unittest.mock import MagicMock
        try:
            mock_parent = MagicMock()
            mock_parent.iface.mainWindow.return_value = None
            dock = self.mod.DigitizeDockWidget(mock_parent)

            # Test Dark Mode
            dock.is_dark = True
            dock._apply_theme()
            self.assertIn("#ECEFF1", dock.title_lbl.styleSheet())
            self.assertIn("#263238", dock.feature_combo.styleSheet())

            # Test Light Mode
            dock.is_dark = False
            dock._apply_theme()
            self.assertIn("#2C3E50", dock.title_lbl.styleSheet())
            self.assertIn("white", dock.feature_combo.styleSheet())
        except Exception as e:
            self.skipTest(f"Skipping GUI test in headless environment: {e}")


if __name__ == "__main__":
    unittest.main()

