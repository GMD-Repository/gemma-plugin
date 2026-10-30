# -*- coding: utf-8 -*-
"""
Unit tests for auto-rerunning full CBMS MV validation when saving edits
resolves all remaining inconsistencies (0 flagged features) for the active rule.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.mocks.qgis_mock import setup_qgis_mock_if_needed

setup_qgis_mock_if_needed()

from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import QApplication

from references.cbms_mv.cbms_mv_fix.common import is_valid_qobject as common_is_valid_qobject
from references.cbms_mv.cbmsmv_dialog import CbmsmvDialog


class TestCbmsMvAutoRerunOnClean(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication([])

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.form2_path = os.path.join(self.tmpdir.name, "form2.csv")
        self.points_path = os.path.join(self.tmpdir.name, "points.geojson")
        with open(self.form2_path, "w", encoding="utf-8") as f:
            f.write("fid,mapid\n1,uuid-001\n")
        with open(self.points_path, "w", encoding="utf-8") as f:
            f.write('{"type": "FeatureCollection", "features": []}')

    def tearDown(self):
        self.tmpdir.cleanup()

    def _make_feature_layer(self, name: str, count: int) -> QgsVectorLayer:
        layer = QgsVectorLayer("Point?crs=EPSG:4326", name, "memory")
        dp = layer.dataProvider()
        dp.addAttributes([
            QgsField("sf_fid", QVariant.Int),
            QgsField("sf_map_uuid", QVariant.String),
        ])
        layer.updateFields()
        feats = []
        for idx in range(1, count + 1):
            feat = QgsFeature(layer.fields())
            feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(121.0 + idx * 0.001, 14.6)))
            feat.setAttribute("sf_fid", idx)
            feat.setAttribute("sf_map_uuid", f"uuid-{idx:03d}")
            feats.append(feat)
        if feats:
            dp.addFeatures(feats)
        layer.updateExtents()
        return layer

    def _build_dialog_harness(self, base_path: str = ""):
        rule_a = {
            "id": "mv_2027_hp_4b_geom__invalid",
            "name": "Mismatched geometry and coordinates",
            "has_base": False,
        }
        rule_b = {
            "id": "mv_2027_hp_4b_bsn_geoid__invalid",
            "name": "Invalid bsn_geoid",
            "has_base": False,
        }

        dialog = MagicMock()
        dialog._is_closing = False
        dialog._pending_json_edits = {}
        dialog._active_review_dock = None
        dialog.iface = None
        dialog.project = None
        dialog.context = MagicMock()
        dialog.should_load_canvas = False
        dialog.should_group_layers = False

        dialog.file_form2.filePath.return_value = self.form2_path
        dialog.file_points.filePath.return_value = self.points_path
        dialog.file_base.filePath.return_value = base_path

        dialog.radio_memory.isChecked.return_value = True
        dialog.radio_file.isChecked.return_value = False
        dialog.chk_summary_report.isChecked.return_value = False

        dialog._rules = [rule_a, rule_b]
        chk_a = MagicMock()
        chk_a.checkState.return_value = Qt.Checked
        chk_b = MagicMock()
        chk_b.checkState.return_value = Qt.Checked
        dialog._rule_checkboxes = {
            rule_a["id"]: chk_a,
            rule_b["id"]: chk_b,
        }

        dialog._result_layers = {
            rule_a["id"]: {
                "layer": self._make_feature_layer(rule_a["id"], 2),
                "rule": rule_a,
                "count": 2,
            },
            rule_b["id"]: {
                "layer": self._make_feature_layer(rule_b["id"], 4),
                "rule": rule_b,
                "count": 4,
            },
        }
        dialog._execution_summary = [
            {"id": rule_a["id"], "name": rule_a["name"], "status": "Flagged", "features_flagged": 2},
            {"id": rule_b["id"], "name": rule_b["name"], "status": "Flagged", "features_flagged": 4},
        ]

        alg_a = MagicMock()
        alg_a.id = rule_a["id"]
        alg_a.parameterDefinitions.return_value = []
        alg_b = MagicMock()
        alg_b.id = rule_b["id"]
        alg_b.parameterDefinitions.return_value = []
        alg_map = {rule_a["id"]: alg_a, rule_b["id"]: alg_b}
        dialog._get_algorithm_instance.side_effect = lambda vid: alg_map.get(vid)

        dialog._get_or_load_main_building_layer.return_value = None
        dialog._find_existing_main_building_layer.return_value = None
        dialog._get_or_load_form2_layer.return_value = None

        # Bind target methods under test from CbmsmvDialog
        dialog._save_changes = CbmsmvDialog._save_changes.__get__(dialog, CbmsmvDialog)
        dialog._discard_changes = CbmsmvDialog._discard_changes.__get__(dialog, CbmsmvDialog)
        dialog._rerun_validation_check = CbmsmvDialog._rerun_validation_check.__get__(dialog, CbmsmvDialog)
        dialog.run_validation = CbmsmvDialog.run_validation.__get__(dialog, CbmsmvDialog)

        return dialog, rule_a, rule_b

    def test_save_triggers_full_rerun_when_remaining_issues_zero(self):
        """When Save re-checks active rule and finds 0 issues, full validation re-runs and refreshes summary."""
        dialog, rule_a, rule_b = self._build_dialog_harness()

        # Attach an open review dock for rule_a to verify it closes cleanly
        mock_dock = MagicMock()
        mock_dock.val_id = rule_a["id"]
        dialog._active_review_dock = mock_dock

        def fake_processing_run(alg_target, params, context=None, feedback=None):
            vid = getattr(alg_target, "id", str(alg_target))
            if rule_a["id"] in vid:
                return {"OUTPUT": self._make_feature_layer(rule_a["id"], 0)}
            # Simulate downstream rule_b dropping from 4 flagged features down to 1!
            return {"OUTPUT": self._make_feature_layer(rule_b["id"], 1)}

        with patch("references.cbms_mv.cbmsmv_dialog.processing.run", side_effect=fake_processing_run) as mock_run, patch(
            "references.cbms_mv.cbmsmv_dialog.QMessageBox"
        ) as mock_msgbox, patch(
            "references.cbms_mv.cbmsmv_dialog.is_valid_qobject",
            side_effect=common_is_valid_qobject,
        ):
            ok = dialog._save_changes(target_val_id=rule_a["id"])

        self.assertTrue(ok)
        # 1 call for single-rule recheck + 2 calls during full validation rerun = 3 calls
        self.assertEqual(mock_run.call_count, 3)

        # Review dock closed
        mock_dock.close.assert_called_once()
        self.assertIsNone(dialog._active_review_dock)

        # Summary refreshed across ALL rules, and 0-count rule_a removed from _result_layers
        summary_by_id = {s["id"]: s for s in dialog._execution_summary}
        self.assertEqual(summary_by_id[rule_a["id"]]["features_flagged"], 0)
        self.assertEqual(summary_by_id[rule_a["id"]]["status"], "Passed")
        self.assertEqual(summary_by_id[rule_b["id"]]["features_flagged"], 1)
        self.assertEqual(summary_by_id[rule_b["id"]]["status"], "Flagged")

        self.assertNotIn(rule_a["id"], dialog._result_layers)
        self.assertIn(rule_b["id"], dialog._result_layers)
        self.assertEqual(dialog._result_layers[rule_b["id"]]["count"], 1)

        # Workspace populated and switched to Results (Summary Overview), single consolidated popup shown
        dialog._populate_results_workspace.assert_called_once()
        dialog._switch_to_results.assert_called_once()
        dialog._jump_to_result_tab.assert_not_called()
        self.assertEqual(mock_msgbox.information.call_count, 1)
        title_arg = mock_msgbox.information.call_args[0][1]
        body_arg = mock_msgbox.information.call_args[0][2]
        self.assertIn("Summary Updated", title_arg)
        self.assertIn(rule_a["id"], body_arg)

    def test_save_with_remaining_issues_updates_single_rule_only(self):
        """When Save re-checks active rule and issues remain (> 0), full validation does not re-run."""
        dialog, rule_a, rule_b = self._build_dialog_harness()

        def fake_processing_run(alg_target, params, context=None, feedback=None):
            return {"OUTPUT": self._make_feature_layer(rule_a["id"], 1)}

        with patch("references.cbms_mv.cbmsmv_dialog.processing.run", side_effect=fake_processing_run) as mock_run, patch(
            "references.cbms_mv.cbmsmv_dialog.QMessageBox"
        ) as mock_msgbox, patch(
            "references.cbms_mv.cbmsmv_dialog.is_valid_qobject",
            side_effect=common_is_valid_qobject,
        ):
            ok = dialog._save_changes(target_val_id=rule_a["id"])

        self.assertTrue(ok)
        # Only the single-rule re-check ran
        self.assertEqual(mock_run.call_count, 1)
        self.assertEqual(dialog._result_layers[rule_a["id"]]["count"], 1)
        # Downstream rule_b remained untouched
        self.assertEqual(dialog._result_layers[rule_b["id"]]["count"], 4)

        dialog._jump_to_result_tab.assert_called_once_with(rule_a["id"])
        dialog._switch_to_results.assert_not_called()
        # Single Re-check Complete dialog shown (else-branch bug fixed)
        self.assertEqual(mock_msgbox.information.call_count, 1)
        self.assertEqual(mock_msgbox.information.call_args[0][1], "Re-check Complete")

    def test_discard_with_zero_issues_does_not_trigger_full_rerun(self):
        """Discarding edits should only refresh the active rule and never trigger a full validation re-run."""
        dialog, rule_a, _ = self._build_dialog_harness()

        def fake_processing_run(alg_target, params, context=None, feedback=None):
            return {"OUTPUT": self._make_feature_layer(rule_a["id"], 0)}

        with patch("references.cbms_mv.cbmsmv_dialog.processing.run", side_effect=fake_processing_run) as mock_run, patch(
            "references.cbms_mv.cbmsmv_dialog.QMessageBox"
        ) as mock_msgbox, patch(
            "references.cbms_mv.cbmsmv_dialog.is_valid_qobject",
            side_effect=common_is_valid_qobject,
        ):
            ok = dialog._discard_changes(target_val_id=rule_a["id"])

        self.assertTrue(ok)
        self.assertEqual(mock_run.call_count, 1)
        dialog._switch_to_results.assert_not_called()
        # Only one popup ("All Issues Resolved"), no duplicate "Re-check Complete" popup
        self.assertEqual(mock_msgbox.information.call_count, 1)
        self.assertEqual(mock_msgbox.information.call_args[0][1], "All Issues Resolved")

    def test_save_and_discard_during_close_skip_recheck(self):
        """Saving or discarding inside closeEvent (_is_closing=True) skips validation re-checks."""
        dialog, rule_a, _ = self._build_dialog_harness()
        dialog._is_closing = True

        with patch("references.cbms_mv.cbmsmv_dialog.processing.run") as mock_run, patch(
            "references.cbms_mv.cbmsmv_dialog.QMessageBox"
        ) as mock_msgbox, patch(
            "references.cbms_mv.cbmsmv_dialog.is_valid_qobject",
            side_effect=common_is_valid_qobject,
        ):
            self.assertTrue(dialog._save_changes(target_val_id=rule_a["id"]))
            self.assertTrue(dialog._discard_changes(target_val_id=rule_a["id"]))

        mock_run.assert_not_called()
        mock_msgbox.information.assert_not_called()

    def test_auto_rerun_silently_skips_missing_base_layer_prompt(self):
        """Auto-rerun skips rules requiring BASE_LAYER without prompting when BASE_LAYER is absent."""
        dialog, rule_a, rule_b = self._build_dialog_harness(base_path="")
        rule_b["has_base"] = True

        def fake_processing_run(alg_target, params, context=None, feedback=None):
            return {"OUTPUT": self._make_feature_layer(rule_a["id"], 0)}

        with patch("references.cbms_mv.cbmsmv_dialog.processing.run", side_effect=fake_processing_run) as mock_run, patch(
            "references.cbms_mv.cbmsmv_dialog.QMessageBox"
        ) as mock_msgbox, patch(
            "references.cbms_mv.cbmsmv_dialog.is_valid_qobject",
            side_effect=common_is_valid_qobject,
        ):
            dialog._save_changes(target_val_id=rule_a["id"])

        # Base layer missing question prompt must NOT appear during auto_rerun
        mock_msgbox.question.assert_not_called()
        # 1 call for single-rule recheck of rule_a + 1 call for rule_a in full rerun (rule_b skipped) = 2 calls
        self.assertEqual(mock_run.call_count, 2)
        self.assertEqual(len(dialog._execution_summary), 1)
        self.assertEqual(dialog._execution_summary[0]["id"], rule_a["id"])


if __name__ == "__main__":
    unittest.main()

