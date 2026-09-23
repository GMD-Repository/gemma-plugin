# -*- coding: utf-8 -*-
"""
Unit tests for candidate building points extraction filtering by execution mode.
Verifies that when running in delineation mode, only delineation candidate building
points are written to EXTRACTED_BUILDINGS_OUTPUT, and when running in merge mode,
only merge candidate/partner building points are written.
"""

import unittest
from qgis.core import (
    QgsFeature,
    QgsFields,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
)
from PyQt5.QtCore import QVariant

from tests.mocks.qgis_mock import setup_qgis_mock_if_needed, QgsProcessingFeedback, QgsProcessingContext
from references.create_enumeration_area.phases.phase8_output import run_phase_8
from references.create_enumeration_area.phases.phase1_init import run_phase_1
from references.create_enumeration_area.eadm_candidates import EADMCandidatesAlgorithm

setup_qgis_mock_if_needed()


class MockSink:
    """In-memory feature sink for capturing output features in unit tests."""

    def __init__(self):
        self.features = []

    def addFeature(self, feature, flags=None):
        self.features.append(QgsFeature(feature))
        return True

    def addFeatures(self, features, flags=None):
        for f in features:
            self.features.append(QgsFeature(f))
        return True


class TestModeBuildingFiltering(unittest.TestCase):
    """Test suite verifying mode-based filtering of building points."""

    def setUp(self):
        self.alg = EADMCandidatesAlgorithm()
        self.alg.initAlgorithm()
        self.feedback = QgsProcessingFeedback()

    def test_parameter_registration(self):
        """Verify EXECUTION_MODE parameter is registered with appropriate enum options."""
        param = self.alg.parameterDefinition(EADMCandidatesAlgorithm.EXECUTION_MODE)
        self.assertIsNotNone(param, "EXECUTION_MODE parameter should be registered on algorithm.")
        self.assertEqual(param.defaultValue(), 0, "Default execution mode must be 0 (All Candidates).")

    def test_phase1_execution_mode_parsing(self):
        """Verify phase1_init parses execution_mode correctly for 0, 1, 2, strings, and default."""
        class MockAlg(EADMCandidatesAlgorithm):
            def parameterAsCrs(self, parameters, name, context):
                return QgsVectorLayer("Polygon?crs=EPSG:4326", "dummy", "memory").crs()

        mock_alg = MockAlg()
        mock_alg.initAlgorithm()

        bldg_layer = QgsVectorLayer("Point?crs=EPSG:4326", "bldg", "memory")
        ea_layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "ea", "memory")
        bar_layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "bar", "memory")

        context = QgsProcessingContext()

        # Mode 1 -> delineation
        params_delin = {
            mock_alg.BARANGAY_INPUT: bar_layer,
            mock_alg.BUILDING_INPUT: bldg_layer,
            mock_alg.PREVIOUS_EA_INPUT: ea_layer,
            mock_alg.EXECUTION_MODE: 1,
        }
        p1_delin = run_phase_1(mock_alg, params_delin, context, self.feedback, None)
        self.assertEqual(p1_delin.get("execution_mode"), "delineation")

        # Mode 2 -> merging
        params_merge = {
            mock_alg.BARANGAY_INPUT: bar_layer,
            mock_alg.BUILDING_INPUT: bldg_layer,
            mock_alg.PREVIOUS_EA_INPUT: ea_layer,
            mock_alg.EXECUTION_MODE: 2,
        }
        p1_merge = run_phase_1(mock_alg, params_merge, context, self.feedback, None)
        self.assertEqual(p1_merge.get("execution_mode"), "merging")

        # Default (Mode 0 or not provided) -> all
        params_all = {
            mock_alg.BARANGAY_INPUT: bar_layer,
            mock_alg.BUILDING_INPUT: bldg_layer,
            mock_alg.PREVIOUS_EA_INPUT: ea_layer,
        }
        p1_all = run_phase_1(mock_alg, params_all, context, self.feedback, None)
        self.assertEqual(p1_all.get("execution_mode"), "all")

    def _setup_pipeline_fixtures(self, exec_mode="all"):
        """Helper to create dummy EAs, buildings, and sinks for Phase 8 testing."""
        export_field_names = [
            "fid", "map_uuid", "geocode", "region", "province",
            "city_mun", "barangay", "code", "name", "ean",
            "hhcount", "bldgcount", "sy", "new_ean", "hh_count",
            "bldg_count", "ea_type", "remarks"
        ]
        fields = QgsFields()
        for fname in export_field_names:
            fields.append(QgsField(fname, QVariant.Int if fname == "fid" else QVariant.String))

        bldg_fields = QgsFields()
        for f in ["fid", "bldg_id", "bldgpoints_value", "pop"]:
            bldg_fields.append(QgsField(f, QVariant.Int if f in ("fid", "bldg_id") else QVariant.Double))

        bldg_layer = QgsVectorLayer("Point?crs=EPSG:4326", "test_bldg", "memory")
        for i in range(bldg_fields.count()):
            bldg_layer.dataProvider().addAttributes([bldg_fields.at(i)])
        bldg_layer.updateFields()

        ea_layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_ea", "memory")
        for i in range(fields.count()):
            ea_layer.dataProvider().addAttributes([fields.at(i)])
        ea_layer.updateFields()

        poly1 = QgsGeometry.fromPolygonXY([[QgsPointXY(0, 0), QgsPointXY(5, 0), QgsPointXY(5, 5), QgsPointXY(0, 5), QgsPointXY(0, 0)]])
        poly2 = QgsGeometry.fromPolygonXY([[QgsPointXY(5, 0), QgsPointXY(10, 0), QgsPointXY(10, 5), QgsPointXY(5, 5), QgsPointXY(5, 0)]])

        # Building dummy points:
        # 1 building in Delineation EA (EA 002000, id 1)
        bldg_delin = {
            "point": QgsPointXY(1.0, 1.0),
            "pop": 2.0,
            "bldgpoints_value": 1.0,
            "attributes": [1, 101, 1.0, 2.0],
            "parent_ean": "002000",
        }
        # 1 building in Merge EA (EA 001000, id 2)
        bldg_merge = {
            "point": QgsPointXY(6.0, 1.0),
            "pop": 1.0,
            "bldgpoints_value": 1.0,
            "attributes": [2, 102, 1.0, 1.0],
            "parent_ean": "001000",
        }

        # EA 1: Delineation Candidate
        ea_delin = {
            "original_id": 1,
            "original_code": "002000",
            "new_ea_code": "002000",
            "parent_barangay": "01101003",
            "geom": poly1,
            "buildings": [bldg_delin],
            "hh_count": 350,
            "bldg_count": 1,
            "from_split": False,
            "from_merge": False,
        }

        # EA 2: Merge Candidate
        ea_merge = {
            "original_id": 2,
            "original_code": "001000",
            "new_ea_code": "001000",
            "parent_barangay": "01101003",
            "geom": poly2,
            "buildings": [bldg_merge],
            "hh_count": 80,
            "bldg_count": 1,
            "from_split": False,
            "from_merge": False,
        }

        p1 = {
            "previous_ea_source": ea_layer,
            "building_source": bldg_layer,
            "target_crs": ea_layer.crs(),
            "area_threshold": 1.0,
            "max_household": 300,
            "min_household": 150,
            "bldg_hh_field": "pop",
            "ea_id_field": "ean",
            "barangay_by_id": {},
            "all_ea_features": [],
            "execution_mode": exec_mode,
        }

        bldg_sink = MockSink()
        delin_cand_sink = MockSink()

        p2 = {
            "out_fields": fields,
            "export_fields": fields,
            "delineation_candidate_ids": {1},
            "merge_candidate_ids": {2},
            "adjacent_ea_ids": set(),
            "delineated_sink": MockSink(),
            "merged_sink": MockSink(),
            "special_ea_sink": None,
            "delin_candidate_sink": delin_cand_sink,
            "extracted_buildings_sink": bldg_sink,
            "delineated_dest_id": "dest_delin",
            "merged_dest_id": "dest_merged",
            "delin_candidate_dest_id": "dest_cand",
            "extracted_buildings_dest_id": "dest_bldg",
            "delin_candidate_feat_count": 1,
            "extracted_bldg_feat_count": 0,
        }

        p3 = {"road_geoms": {}, "river_geoms": {}}
        p4 = {}
        p7 = {"eas": [ea_delin, ea_merge]}

        return p1, p2, p3, p4, p7, bldg_sink

    def test_phase8_filters_buildings_in_delineation_mode(self):
        """In delineation mode, phase8_output only writes buildings belonging to delineation candidates."""
        p1, p2, p3, p4, p7, bldg_sink = self._setup_pipeline_fixtures(exec_mode="delineation")

        run_phase_8(self.alg, {}, None, self.feedback, None, p1, p2, p3, p4, p7)

        # Must only contain 1 building point (from EA 1 / 002000), not the merge candidate point (EA 2 / 001000)
        self.assertEqual(len(bldg_sink.features), 1, "Delineation mode must only extract delineation candidate buildings.")
        feat = bldg_sink.features[0]
        self.assertEqual(feat.attribute("parent_ean"), "002000")
        self.assertEqual(feat.attribute("merge_role"), "Delineation Candidate")

    def test_phase8_filters_buildings_in_merging_mode(self):
        """In merging mode, phase8_output only writes buildings belonging to merge candidates/partners."""
        p1, p2, p3, p4, p7, bldg_sink = self._setup_pipeline_fixtures(exec_mode="merging")

        run_phase_8(self.alg, {}, None, self.feedback, None, p1, p2, p3, p4, p7)

        # Must only contain 1 building point (from EA 2 / 001000), not the delineation candidate point
        self.assertEqual(len(bldg_sink.features), 1, "Merging mode must only extract merge candidate buildings.")
        feat = bldg_sink.features[0]
        self.assertEqual(feat.attribute("parent_ean"), "001000")
        self.assertEqual(feat.attribute("merge_role"), "Candidate")

    def test_phase8_includes_all_buildings_in_all_mode(self):
        """In 'all' mode, phase8_output writes buildings for both delineation and merge candidates."""
        p1, p2, p3, p4, p7, bldg_sink = self._setup_pipeline_fixtures(exec_mode="all")

        run_phase_8(self.alg, {}, None, self.feedback, None, p1, p2, p3, p4, p7)

        # Must contain both building points (2 total)
        self.assertEqual(len(bldg_sink.features), 2, "'all' mode must extract buildings for both candidate types.")
        eans = {f.attribute("parent_ean") for f in bldg_sink.features}
        self.assertEqual(eans, {"002000", "001000"})

    def test_dialog_pipeline_populates_execution_mode(self):
        """Verify dialog.run_pipeline sets parameters['EXECUTION_MODE'] correctly per mode."""
        import inspect
        from references.create_enumeration_area.dialog import EALauncherDialog

        src = inspect.getsource(EALauncherDialog.run_pipeline)
        self.assertIn("'EXECUTION_MODE': exec_mode_val", src)
        self.assertIn("if mode == \"delineation\":", src)
        self.assertIn("exec_mode_val = 1", src)
        self.assertIn("elif mode == \"merging\":", src)
        self.assertIn("exec_mode_val = 2", src)


if __name__ == "__main__":
    unittest.main()
