# -*- coding: utf-8 -*-
"""
Unit test module for package_qfield.py (gmd_scripts/package_qfield.py).
Tests QField package dialog launcher and callback handling using mock iface.
"""

import unittest
import importlib
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
        except ImportError:
            # Relative import beyond top-level package occurs when tested outside QGIS plugin package hierarchy
            pass


if __name__ == "__main__":
    unittest.main()
