# -*- coding: utf-8 -*-
"""
Unit tests for verifying strict output isolation between:
- Tab 2 - Sub-tab 1: Proposed Delineation (execution_mode = 1 / "delineation")
- Tab 2 - Sub-tab 2: Proposed Merging (execution_mode = 2 / "merging")

Ensures:
1. In Delineation mode, MERGED_OUTPUT is never created, never processed, and never exported.
2. In Merging mode, DELINEATED_OUTPUT, DELINEATION_CANDIDATE_OUTPUT, and proposed cut lines (_eadel_update) are never created, never processed, and never exported.
3. In Dialog run_pipeline, scratch sinks are strictly partitioned by sub-tab mode.
"""

import unittest
from unittest.mock import MagicMock, patch
from qgis.core import (
    QgsFeature,
    QgsFields,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
    QgsProject,
)
from PyQt5.QtCore import QVariant

from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, QgsProcessingFeedback, QgsProcessingContext
from references.create_enumeration_area.phases.phase2_candidates import run_phase_2
from references.create_enumeration_area.phases.phase5_delineate import run_phase_5
from references.create_enumeration_area.phases.phase6_merge import run_phase_6
from references.create_enumeration_area.phases.phase8_output import run_phase_8
from references.create_enumeration_area.eadm_candidates import EADMCandidatesAlgorithm

setup_qgis_mock_if_needed()


class TestModeOutputIsolation(unittest.TestCase):
    """Test suite verifying output isolation between Delineation and Merging execution modes."""

    def setUp(self):
        self.alg = EADMCandidatesAlgorithm()
        self.alg.initAlgorithm()
        self.feedback = QgsProcessingFeedback()
        self.context = QgsProcessingContext()

    def test_phase2_sink_isolation_delineation_mode(self):
        """In delineation mode, phase 2 must NOT create merged_sink even if parameter is present."""
        fields = QgsFields()
        fields.append(QgsField("geocode", QVariant.String))
        fields.append(QgsField("ean", QVariant.String))
        fields.append(QgsField("hhcount", QVariant.Double))

        bldg_layer = QgsVectorLayer("Point?crs=EPSG:4326", "bldg", "memory")
        ea_layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "ea", "memory")
        ea_layer.dataProvider().addAttributes(fields)
        ea_layer.updateFields()
        bar_layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "bar", "memory")

        p1 = {
            "execution_mode": "delineation",
            "barangay_source": bar_layer,
            "building_source": bldg_layer,
            "previous_ea_source": ea_layer,
            "gap_source": None,
            "overlap_source": None,
            "min_household": 100,
            "max_household": 300,
            "target_household": 200,
            "target_crs": ea_layer.crs(),
            "ea_id_field": "ean",
            "household_field": "hhcount",
            "bldg_hh_field": "hhcount",
            "barangay_id_field": "bgy",
            "bar_geocode_field": "geocode",
            "eadel_indi_col_idx": -1,
            "merge_indi_col_idx": -1,
            "all_ea_features": [],
            "special_ea_info": {},
            "special_ea_ids": set(),
            "output_layer_name": "01234_delineated_ea2026",
            "transform": None,
            "preview_only": False,
            "barangay_index": None,
            "barangay_by_id": {},
        }

        # Parameters provide both sinks
        parameters = {
            self.alg.DELINEATED_OUTPUT: "memory:delineated",
            self.alg.MERGED_OUTPUT: "memory:merged",
            self.alg.DELINEATION_CANDIDATE_OUTPUT: "memory:delin_cand",
            self.alg.EXTRACTED_BUILDINGS_OUTPUT: "memory:bldgs",
        }

        multi_feedback = MagicMock()
        multi_feedback.isCanceled.return_value = False
        p2 = run_phase_2(self.alg, parameters, self.context, self.feedback, multi_feedback, p1)

        # In delineation mode, merged_sink must be None and MERGED_OUTPUT omitted from outputs!
        self.assertIsNone(p2.get("merged_sink"), "merged_sink must be None in delineation mode")
        self.assertNotIn(self.alg.MERGED_OUTPUT, p2["outputs"], "MERGED_OUTPUT must not be in phase 2 outputs")
        self.assertIsNotNone(p2.get("delineated_sink"), "delineated_sink must be created in delineation mode")
        self.assertIsNotNone(p2.get("delin_candidate_sink"), "delin_candidate_sink must be created in delineation mode")

    def test_phase2_sink_isolation_merging_mode(self):
        """In merging mode, phase 2 must NOT create delineated_sink or delin_candidate_sink."""
        fields = QgsFields()
        fields.append(QgsField("geocode", QVariant.String))
        fields.append(QgsField("ean", QVariant.String))
        fields.append(QgsField("hhcount", QVariant.Double))

        bldg_layer = QgsVectorLayer("Point?crs=EPSG:4326", "bldg", "memory")
        ea_layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "ea", "memory")
        ea_layer.dataProvider().addAttributes(fields)
        ea_layer.updateFields()
        bar_layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "bar", "memory")

        p1 = {
            "execution_mode": "merging",
            "barangay_source": bar_layer,
            "building_source": bldg_layer,
            "previous_ea_source": ea_layer,
            "gap_source": None,
            "overlap_source": None,
            "min_household": 100,
            "max_household": 300,
            "target_household": 200,
            "target_crs": ea_layer.crs(),
            "ea_id_field": "ean",
            "household_field": "hhcount",
            "bldg_hh_field": "hhcount",
            "barangay_id_field": "bgy",
            "bar_geocode_field": "geocode",
            "eadel_indi_col_idx": -1,
            "merge_indi_col_idx": -1,
            "all_ea_features": [],
            "special_ea_info": {},
            "special_ea_ids": set(),
            "output_layer_name": "01234_merged_ea2026",
            "transform": None,
            "preview_only": False,
            "barangay_index": None,
            "barangay_by_id": {},
        }

        # Parameters provide all sinks
        parameters = {
            self.alg.DELINEATED_OUTPUT: "memory:delineated",
            self.alg.MERGED_OUTPUT: "memory:merged",
            self.alg.DELINEATION_CANDIDATE_OUTPUT: "memory:delin_cand",
            self.alg.EXTRACTED_BUILDINGS_OUTPUT: "memory:bldgs",
        }

        multi_feedback = MagicMock()
        multi_feedback.isCanceled.return_value = False
        p2 = run_phase_2(self.alg, parameters, self.context, self.feedback, multi_feedback, p1)

        # In merging mode, delineated sinks must be None and omitted from outputs!
        self.assertIsNone(p2.get("delineated_sink"), "delineated_sink must be None in merging mode")
        self.assertIsNone(p2.get("delin_candidate_sink"), "delin_candidate_sink must be None in merging mode")
        self.assertNotIn(self.alg.DELINEATED_OUTPUT, p2["outputs"], "DELINEATED_OUTPUT must not be in phase 2 outputs")
        self.assertNotIn(self.alg.DELINEATION_CANDIDATE_OUTPUT, p2["outputs"], "DELINEATION_CANDIDATE_OUTPUT must not be in outputs")
        self.assertIsNotNone(p2.get("merged_sink"), "merged_sink must be created in merging mode")

    def test_phase5_skips_in_merging_mode(self):
        """Phase 5 must skip delineation splitting and return split_eas == eas when execution_mode is merging."""
        dummy_eas = [{"original_id": 1, "hh_count": 500, "original_code": "001000"}]
        p1 = {"execution_mode": "merging", "min_household": 100, "max_household": 300, "target_household": 200, "snap_tolerance": 15.0, "densify_dist": 5.0, "area_threshold": 1.0, "eadel_indi_col_idx": -1}
        p2 = {"full_ea_by_id": {}, "delineation_candidate_ids": {1}, "merge_candidate_ids": set(), "delineation_candidate_hhdivthres": {}}
        p3 = {"road_index": None, "road_geoms": {}, "river_index": None, "river_geoms": {}}
        p4 = {"eas": dummy_eas}

        res = run_phase_5(self.alg, {}, self.context, self.feedback, None, p1, p2, p3, p4)
        self.assertEqual(res["split_eas"], dummy_eas, "Phase 5 should directly return input eas in merging mode")

    def test_phase6_skips_in_delineation_mode(self):
        """Phase 6 must skip merging and return merged_eas == split_eas when execution_mode is delineation."""
        dummy_split_eas = [{"original_id": 1, "hh_count": 50, "original_code": "001000", "parent_barangay": "01234001"}]
        p1 = {"execution_mode": "delineation", "min_household": 100, "max_household": 300, "eadel_indi_col_idx": -1}
        p2 = {"full_ea_by_id": {}, "delineation_candidate_ids": set(), "merge_candidate_ids": {1}}
        p5 = {"split_eas": dummy_split_eas}

        res = run_phase_6(self.alg, {}, self.context, self.feedback, None, p1, p2, p5)
        self.assertEqual(res["merged_eas"], dummy_split_eas, "Phase 6 should directly return split_eas in delineation mode")

    def test_phase8_omits_splitting_lines_and_delineated_outputs_in_merging_mode(self):
        """Phase 8 in merging mode must NOT create _eadel_update layer or return DELINEATED_OUTPUT."""
        QgsProject.instance().removeAllMapLayers()

        fields = QgsFields()
        fields.append(QgsField("geocode", QVariant.String))
        fields.append(QgsField("ean", QVariant.String))
        dummy_layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test", "memory")

        p1 = {
            "execution_mode": "merging",
            "previous_ea_source": dummy_layer,
            "barangay_source": dummy_layer,
            "building_source": dummy_layer,
            "out_fields": fields,
            "target_crs": dummy_layer.crs(),
            "area_threshold": 1.0,
            "max_household": 300,
            "min_household": 100,
            "household_field": "hhcount",
            "bldgcount_field": "bldgcount",
            "output_hh_field": "hhcount",
            "bldg_hh_field": "hhcount",
            "ea_id_field": "ean",
            "barangay_by_id": {},
        }
        p2 = {
            "delineation_candidate_ids": {1},
            "merge_candidate_ids": set(),
            "adjacent_ea_ids": set(),
            "special_ea_info": {},
            "delineated_sink": None,
            "merged_sink": MagicMock(),
            "special_ea_sink": None,
            "extracted_buildings_sink": None,
            "delineated_dest_id": "delin_id",
            "merged_dest_id": "merged_id",
            "extracted_buildings_dest_id": None,
            "delin_candidate_dest_id": "delin_cand_id",
            "delin_candidate_feat_count": 1,
            "extracted_bldg_feat_count": 0,
        }
        p3 = {"road_geoms": {}, "river_geoms": {}}
        p4 = {"max_ea_number": {}, "barangay_sibling_ean_codes": {}}
        p7 = {
            "eas": [],
            "split_eas": [],
            "proposed_lines": [{"ea_id": 1, "geom": QgsGeometry.fromPolylineXY([QgsPointXY(0, 0), QgsPointXY(1, 1)])}],
        }

        outputs = run_phase_8(
            alg=self.alg,
            parameters={},
            context=self.context,
            feedback=self.feedback,
            multi_feedback=None,
            p1=p1,
            p2=p2,
            p3=p3,
            p4=p4,
            p7=p7,
        )

        # 1. DELINEATED_OUTPUT must NOT be in final_outputs
        self.assertNotIn(self.alg.DELINEATED_OUTPUT, outputs)
        self.assertNotIn(self.alg.DELINEATION_CANDIDATE_OUTPUT, outputs)

        # 2. No _eadel_update layer must exist in QgsProject
        line_layers = [lyr for lyr in QgsProject.instance().mapLayers().values() if "_eadel_update" in lyr.name()]
        self.assertEqual(len(line_layers), 0, "_eadel_update layer must not be created in merging mode")

    def test_dialog_run_pipeline_parameters_partitioning(self):
        """Verify that dialog.run_pipeline creates parameter dictionaries strictly excluding unwanted sinks."""
        from references.create_enumeration_area.dialog import EALauncherDialog

        mock_dlg = MagicMock()
        mock_dlg._safe_get_layer.return_value = QgsVectorLayer("Polygon?crs=EPSG:4326", "test", "memory")
        mock_dlg._extract_5digit_geocode.return_value = "01234"
        mock_dlg.tolerance_spin.value.return_value = 15.0
        mock_dlg.enable_thresholds_chk.isChecked.return_value = False
        mock_dlg.min_hh_spin.value.return_value = 100
        mock_dlg.max_hh_spin.value.return_value = 300
        mock_dlg.compact_chk.isChecked.return_value = True
        mock_dlg.allow_candidate_merge_chk.isChecked.return_value = True
        mock_dlg.sliver_combo.currentIndex.return_value = 0
        mock_dlg.crs_widget.crs.return_value = QgsVectorLayer("Polygon?crs=EPSG:4326", "test", "memory").crs()
        mock_dlg.output_folder_widget.filePath.return_value = "C:/tmp"
        mock_dlg.merge_output_folder_widget.filePath.return_value = "C:/tmp"

        captured_params = {}

        def fake_run_and_load(alg, parameters, context=None, feedback=None):
            captured_params.update(parameters)
            return {}

        with patch("qgis.processing.runAndLoadResults", side_effect=fake_run_and_load), \
             patch("os.makedirs"):

            # Run delineation mode
            EALauncherDialog.run_pipeline(mock_dlg, mode="delineation")
            self.assertIn("DELINEATED_OUTPUT", captured_params)
            self.assertIn("DELINEATION_CANDIDATE_OUTPUT", captured_params)
            self.assertIn("EXTRACTED_BUILDINGS_OUTPUT", captured_params)
            self.assertNotIn("MERGED_OUTPUT", captured_params, "MERGED_OUTPUT must be omitted in delineation mode")

            # Run merging mode
            captured_params.clear()
            EALauncherDialog.run_pipeline(mock_dlg, mode="merging")
            self.assertIn("MERGED_OUTPUT", captured_params)
            self.assertIn("EXTRACTED_BUILDINGS_OUTPUT", captured_params)
            self.assertNotIn("DELINEATED_OUTPUT", captured_params, "DELINEATED_OUTPUT must be omitted in merging mode")
            self.assertNotIn("DELINEATION_CANDIDATE_OUTPUT", captured_params, "DELINEATION_CANDIDATE_OUTPUT must be omitted in merging mode")


if __name__ == "__main__":
    unittest.main()
