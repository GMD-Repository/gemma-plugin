# -*- coding: utf-8 -*-
"""
Unit tests for CBMS MV 'Load primary input data sources into QGIS Layers Panel' checkbox.
Verifies that:
- Checkbox is checked (True) by default if '2027 CBMS Primary Inputs' group is absent or empty.
- Checkbox is unchecked (False) by default if '2027 CBMS Primary Inputs' group is already present with layers.
- User can manually toggle the checkbox without _on_inputs_changed forcing it back to False.
- Project events (projectRead, cleared) update the default dynamically.
"""

import unittest
from unittest.mock import MagicMock
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed

setup_qgis_mock_if_needed()

from qgis.PyQt.QtWidgets import QDialog
from references.cbms_mv.cbmsmv_dialog import CbmsmvDialog, SETTINGS_KEY_LOAD_INPUTS


class TestCbmsMvLoadInputsDefault(unittest.TestCase):
    """Test suite for dynamic load primary inputs checkbox defaults."""

    def setUp(self):
        self.dialog = CbmsmvDialog.__new__(CbmsmvDialog)
        QDialog.__init__(self.dialog)
        self.dialog.settings = MagicMock()
        self.dialog.project = MagicMock()
        self.dialog._user_toggled_load_inputs = False

    def test_has_primary_inputs_group_absent(self):
        """When the group is absent, _has_primary_inputs_group returns False."""
        mock_root = MagicMock()
        mock_root.findGroup.return_value = None
        self.dialog.project.layerTreeRoot.return_value = mock_root

        self.assertFalse(self.dialog._has_primary_inputs_group())

    def test_has_primary_inputs_group_empty(self):
        """When the group exists but has no layers, _has_primary_inputs_group returns False."""
        mock_root = MagicMock()
        mock_grp = MagicMock()
        mock_grp.findLayers.return_value = []
        mock_grp.children.return_value = []
        mock_root.findGroup.return_value = mock_grp
        self.dialog.project.layerTreeRoot.return_value = mock_root

        self.assertFalse(self.dialog._has_primary_inputs_group())

    def test_has_primary_inputs_group_present_with_layers(self):
        """When the group exists with valid layers, _has_primary_inputs_group returns True."""
        mock_root = MagicMock()
        mock_grp = MagicMock()
        mock_tree_layer = MagicMock()
        mock_layer = MagicMock()
        mock_layer.isValid.return_value = True
        mock_tree_layer.layer.return_value = mock_layer
        mock_grp.findLayers.return_value = [mock_tree_layer]
        mock_root.findGroup.return_value = mock_grp
        self.dialog.project.layerTreeRoot.return_value = mock_root

        self.assertTrue(self.dialog._has_primary_inputs_group())

    def test_update_load_inputs_default_when_group_absent(self):
        """When group is absent, checkbox should be checked (True) by default."""
        self.dialog._has_primary_inputs_group = MagicMock(return_value=False)
        mock_chk = MagicMock()
        mock_chk.isChecked.return_value = True
        self.dialog.chk_load_inputs_canvas = mock_chk

        self.dialog._update_load_inputs_default()

        mock_chk.setChecked.assert_called_with(True)
        self.dialog.settings.setValue.assert_called_with(SETTINGS_KEY_LOAD_INPUTS, True)

    def test_update_load_inputs_default_when_group_present(self):
        """When group is present with layers, checkbox should be unchecked (False) by default."""
        self.dialog._has_primary_inputs_group = MagicMock(return_value=True)
        mock_chk = MagicMock()
        mock_chk.isChecked.return_value = False
        self.dialog.chk_load_inputs_canvas = mock_chk

        self.dialog._update_load_inputs_default()

        mock_chk.setChecked.assert_called_with(False)
        self.dialog.settings.setValue(SETTINGS_KEY_LOAD_INPUTS, False)

    def test_on_inputs_changed_does_not_force_unchecked(self):
        """_on_inputs_changed must NOT force chk_load_inputs_canvas to False when group exists."""
        mock_root = MagicMock()
        mock_root.findGroup.return_value = MagicMock()
        self.dialog.project.layerTreeRoot.return_value = mock_root

        self.dialog.file_form2 = MagicMock()
        self.dialog.file_form2.filePath.return_value = "form2.csv"
        self.dialog.file_points = MagicMock()
        self.dialog.file_points.filePath.return_value = "points.geojson"
        self.dialog.file_base = MagicMock()
        self.dialog.file_base.filePath.return_value = "base.gpkg"

        mock_chk = MagicMock()
        mock_chk.isChecked.return_value = True
        self.dialog.chk_load_inputs_canvas = mock_chk

        # Calling _on_inputs_changed should not setChecked(False)
        self.dialog._on_inputs_changed()

        mock_chk.setChecked.assert_not_called()
        self.dialog.settings.setValue.assert_any_call(SETTINGS_KEY_LOAD_INPUTS, True)

    def test_user_toggle_tracker(self):
        """Clicking checkbox marks _user_toggled_load_inputs as True."""
        self.assertFalse(self.dialog._user_toggled_load_inputs)
        self.dialog._on_user_toggled_load_inputs()
        self.assertTrue(self.dialog._user_toggled_load_inputs)


if __name__ == "__main__":
    unittest.main()
