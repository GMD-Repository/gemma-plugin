# -*- coding: utf-8 -*-
"""
Unit test module for EA Delineation and Merging dialog refresh functionality.
Verifies that opening/refreshing the dialog resets all inputs, process states,
logs, KPI cards, results tables, and summaries across Tab 1, Tab 2, and Tab 3.
"""

import unittest
from unittest.mock import MagicMock, patch
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, MockGenericClass

setup_qgis_mock_if_needed()


class TestEADialogRefresh(unittest.TestCase):
    """Test suite for EALauncherDialog refresh lifecycle methods."""

    def test_refresh_all_methods_exist(self):
        """Verify that refresh methods exist on EALauncherDialog class."""
        from references.create_enumeration_area.dialog import EALauncherDialog

        self.assertTrue(hasattr(EALauncherDialog, "refresh_all"), "EALauncherDialog must have refresh_all method")
        self.assertTrue(hasattr(EALauncherDialog, "_pre_ea_refresh"), "EALauncherDialog must have _pre_ea_refresh method")
        self.assertTrue(hasattr(EALauncherDialog, "_create_ea_refresh"), "EALauncherDialog must have _create_ea_refresh method")
        self.assertTrue(hasattr(EALauncherDialog, "_ea_merge_refresh"), "EALauncherDialog must have _ea_merge_refresh method")

    def test_refresh_all_calls_sub_refreshes(self):
        """Verify that refresh_all calls _pre_ea_refresh, _create_ea_refresh, and _ea_merge_refresh."""
        from references.create_enumeration_area.dialog import EALauncherDialog

        # Create a mock instance with methods mocked
        mock_dlg = MagicMock(spec=EALauncherDialog)
        # Bind the real refresh_all method to mock_dlg
        EALauncherDialog.refresh_all(mock_dlg)

        mock_dlg._pre_ea_refresh.assert_called_once()
        mock_dlg._create_ea_refresh.assert_called_once()
        mock_dlg._ea_merge_refresh.assert_called_once()

    def test_pre_ea_refresh_resets_state(self):
        """Verify that _pre_ea_refresh resets controls, logs, tables, and runs auto-detection."""
        from references.create_enumeration_area.dialog import EALauncherDialog

        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.pre_ea_bgy_combo = MagicMock()
        mock_dlg.pre_ea_ea_combo = MagicMock()
        mock_dlg.pre_ea_output_folder_widget = MagicMock()
        mock_dlg.pre_ea_gap_tol_spin = MagicMock()
        mock_dlg.pre_ea_clip_chk = MagicMock()
        mock_dlg.pre_ea_resolve_overlaps_chk = MagicMock()
        mock_dlg.pre_ea_detect_gaps_chk = MagicMock()
        mock_dlg.pre_ea_assign_gaps_chk = MagicMock()
        mock_dlg.pre_ea_progress_bar = MagicMock()
        mock_dlg.pre_ea_cancel_btn = MagicMock()
        mock_dlg.pre_ea_status_banner = MagicMock()
        mock_dlg.pre_ea_results_table = MagicMock()
        mock_dlg.pre_ea_log_console = MagicMock()
        mock_dlg.pre_ea_right_tabs = MagicMock()
        mock_dlg._pre_ea_sum_status_lbl = MagicMock()
        mock_dlg._pre_ea_sum_bgy_val = MagicMock()

        # Call real method
        EALauncherDialog._pre_ea_refresh(mock_dlg)

        mock_dlg.pre_ea_bgy_combo.setLayer.assert_called_once_with(None)
        mock_dlg.pre_ea_ea_combo.setLayer.assert_called_once_with(None)
        mock_dlg.pre_ea_output_folder_widget.setFilePath.assert_called_once_with("")
        mock_dlg.pre_ea_gap_tol_spin.setValue.assert_called_once_with(1.0)
        mock_dlg.pre_ea_progress_bar.setValue.assert_called_once_with(0)
        mock_dlg.pre_ea_cancel_btn.setEnabled.assert_called_once_with(False)
        mock_dlg.pre_ea_results_table.setRowCount.assert_called_once_with(0)
        mock_dlg.pre_ea_log_console.clear.assert_called_once()
        mock_dlg._pre_ea_auto_detect_layers.assert_called_once()
        mock_dlg.pre_ea_right_tabs.setCurrentIndex.assert_called_once_with(0)

    def test_create_ea_refresh_resets_state(self):
        """Verify that _create_ea_refresh resets controls, logs, KPI cards, and runs auto-detection."""
        from references.create_enumeration_area.dialog import EALauncherDialog

        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.all_delineation_candidates = ["item1"]
        mock_dlg.all_merge_candidates = ["item2"]
        mock_dlg.bar_combo = MagicMock()
        mock_dlg.bldg_combo = MagicMock()
        mock_dlg.prev_ea_combo = MagicMock()
        mock_dlg.enable_thresholds_chk = MagicMock()
        mock_dlg.min_hh_spin = MagicMock()
        mock_dlg.max_hh_spin = MagicMock()
        mock_dlg.tolerance_spin = MagicMock()
        mock_dlg.compact_chk = MagicMock()
        mock_dlg.allow_candidate_merge_chk = MagicMock()
        mock_dlg.sliver_combo = MagicMock()
        mock_dlg.crs_widget = MagicMock()
        mock_dlg.params_group = MagicMock()
        mock_dlg.delineated_edit = MagicMock()
        mock_dlg.merged_edit = MagicMock()
        mock_dlg.search_edit = MagicMock()
        mock_dlg.progress_bar = MagicMock()
        mock_dlg.cancel_btn = MagicMock()
        mock_dlg.run_btn = MagicMock()
        mock_dlg.status_banner = MagicMock()
        mock_dlg.kpi_delin_val = MagicMock()
        mock_dlg.kpi_merge_val = MagicMock()
        mock_dlg.delineation_table = MagicMock()
        mock_dlg.merge_table = MagicMock()
        mock_dlg.log_console = MagicMock()
        mock_dlg.tab_widget = MagicMock()

        # prev_ea_combo has no layer after reset
        mock_dlg._safe_get_layer.return_value = None

        EALauncherDialog._create_ea_refresh(mock_dlg)

        self.assertEqual(len(mock_dlg.all_delineation_candidates), 0)
        self.assertEqual(len(mock_dlg.all_merge_candidates), 0)
        mock_dlg.enable_thresholds_chk.setChecked.assert_called_once_with(False)
        mock_dlg.min_hh_spin.setValue.assert_called_once_with(100)
        mock_dlg.max_hh_spin.setValue.assert_called_once_with(300)
        mock_dlg.params_group.setCollapsed.assert_called_once_with(True)
        mock_dlg.progress_bar.setValue.assert_called_once_with(0)
        mock_dlg.cancel_btn.setEnabled.assert_called_once_with(False)
        mock_dlg.run_btn.setEnabled.assert_called_once_with(True)
        mock_dlg.kpi_delin_val.setText.assert_called_once_with("0")
        mock_dlg.kpi_merge_val.setText.assert_called_once_with("0")
        mock_dlg.delineation_table.setRowCount.assert_called_once_with(0)
        mock_dlg.merge_table.setRowCount.assert_called_once_with(0)
        mock_dlg.log_console.clear.assert_called_once()
        mock_dlg.auto_detect_layers.assert_called_once()
        mock_dlg.tab_widget.setCurrentIndex.assert_called_once_with(0)

    def test_ea_merge_refresh_resets_state(self):
        """Verify that _ea_merge_refresh resets controls, replacement list, summaries, and logs."""
        from references.create_enumeration_area.dialog import EALauncherDialog

        mock_dlg = MagicMock(spec=EALauncherDialog)
        mock_dlg.ea_merge_ea_combo = MagicMock()
        mock_dlg.ea_merge_output_folder_widget = MagicMock()
        mock_dlg.ea_merge_layers_list = MagicMock()
        mock_dlg.ea_merge_progress_bar = MagicMock()
        mock_dlg.ea_merge_cancel_btn = MagicMock()
        mock_dlg.ea_merge_run_btn = MagicMock()
        mock_dlg.ea_merge_status_banner = MagicMock()
        mock_dlg.ea_merge_log_console = MagicMock()
        mock_dlg.ea_merge_right_tabs = MagicMock()
        mock_dlg._ea_merge_sum_status_lbl = MagicMock()
        mock_dlg._ea_merge_sum_geocode_val = MagicMock()

        EALauncherDialog._ea_merge_refresh(mock_dlg)

        self.assertEqual(mock_dlg._ea_merge_replacement_layers, [])
        mock_dlg.ea_merge_layers_list.clear.assert_called_once()
        mock_dlg.ea_merge_output_folder_widget.setFilePath.assert_called_once_with("")
        mock_dlg.ea_merge_progress_bar.setValue.assert_called_once_with(0)
        mock_dlg.ea_merge_cancel_btn.setEnabled.assert_called_once_with(False)
        mock_dlg.ea_merge_run_btn.setEnabled.assert_called_once_with(True)
        mock_dlg._ea_merge_sum_status_lbl.setText.assert_called_once_with("Status: READY")
        mock_dlg.ea_merge_log_console.clear.assert_called_once()
        mock_dlg._ea_merge_auto_detect_ea_layer.assert_called_once()
        mock_dlg.ea_merge_right_tabs.setCurrentIndex.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
