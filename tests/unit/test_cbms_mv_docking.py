# -*- coding: utf-8 -*-
"""
Unit tests for CBMS MV tool window docking, undocking, dragging, and lifecycle.
Verifies that:
- Dragging a docked window (which alters topLevel / floating state) does NOT close the dialog.
- Central container is never destroyed and is always reparented back to dialog on close/undock.
- Dock widget uses dedicated CbmsmvDockWidget to only trigger close when [X] is explicitly clicked.
- Relaunching dialog after docking or undocking works reliably.
"""

import unittest
from unittest.mock import MagicMock
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed

setup_qgis_mock_if_needed()

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QCloseEvent
from qgis.PyQt.QtWidgets import QDialog, QWidget, QVBoxLayout
from references.cbms_mv.cbmsmv_dialog import CbmsmvDialog, CbmsmvDockWidget


class TestCbmsMvDocking(unittest.TestCase):
    """Test suite for CBMS MV docking and undocking robustness."""

    def setUp(self):
        self.dialog = CbmsmvDialog.__new__(CbmsmvDialog)
        QDialog.__init__(self.dialog)
        self.dialog.iface = MagicMock()
        self.dialog.settings = MagicMock()
        self.dialog._dialog_layout = QVBoxLayout(self.dialog)
        self.dialog._central_container = QWidget(self.dialog)
        self.dialog._dialog_layout.addWidget(self.dialog._central_container)
        self.dialog._is_docked = False
        self.dialog._is_switching_dock = False
        self.dialog._is_closing = False
        self.dialog._dock_widget = None
        self.dialog.btn_dock = MagicMock()
        self.dialog.lbl_footer_status = MagicMock()
        self.dialog._pending_json_edits = {}
        self.dialog.project = None

    def test_dock_and_undock_reparenting(self):
        """dock_window moves central container to dock widget, and undock_window restores it."""
        self.dialog.dock_window()
        self.assertTrue(self.dialog._is_docked)
        self.assertIsNotNone(self.dialog._dock_widget)
        self.assertIsInstance(self.dialog._dock_widget, CbmsmvDockWidget)
        self.assertEqual(self.dialog._central_container.parent(), self.dialog._dock_widget)

        self.dialog.undock_window()
        self.assertFalse(self.dialog._is_docked)
        self.assertEqual(self.dialog._central_container.parent(), self.dialog)

    def test_dragging_dock_top_level_changed_does_not_close_dialog(self):
        """Floating or moving dock widget via dragging must not close the dialog or destroy container."""
        self.dialog.dock_window()
        dock = self.dialog._dock_widget
        close_spy = MagicMock()
        self.dialog.close = close_spy

        # Simulate user dragging dock widget to float
        self.dialog._on_dock_top_level_changed(True)
        close_spy.assert_not_called()
        self.assertTrue(self.dialog._is_docked)
        self.assertEqual(self.dialog._central_container.parent(), dock)

        # Simulate user dragging dock widget back to docked area
        self.dialog._on_dock_top_level_changed(False)
        close_spy.assert_not_called()
        self.assertTrue(self.dialog._is_docked)

    def test_dock_closed_triggers_dialog_close(self):
        """Clicking close button [X] on dock widget triggers dialog.close()."""
        self.dialog.dock_window()
        close_spy = MagicMock()
        self.dialog.close = close_spy

        self.dialog._on_dock_closed()
        close_spy.assert_called_once()

    def test_restore_central_container_on_close(self):
        """closeEvent restores central container to dialog so it is not deleted with dock widget."""
        self.dialog.dock_window()
        dock = self.dialog._dock_widget

        # Simulate closing the dialog
        mock_event = QCloseEvent()
        self.dialog._find_existing_main_building_layer = MagicMock(return_value=None)
        self.dialog.closeEvent(mock_event)

        # Central container must be reparented back to self, not deleted
        self.assertEqual(self.dialog._central_container.parent(), self.dialog)
        self.assertIsNone(self.dialog._dock_widget)
        self.assertFalse(self.dialog._is_docked)


if __name__ == "__main__":
    unittest.main()
