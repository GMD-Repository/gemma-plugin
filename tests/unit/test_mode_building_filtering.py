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
    QgsSpatialIndex,
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

    def test_phase8_delineation_candidate_takes_precedence_over_adjacent_partner(self):
        """Verify that an EA in both delineation_candidate_ids and adjacent_ea_ids gets 'Delineation Candidate' role."""
        p1, p2, p3, p4, p7, bldg_sink = self._setup_pipeline_fixtures(exec_mode="delineation")
        # Simulate EA 1 also being in adjacent_ea_ids (e.g. adjacent to merge candidate EA 2)
        p2["adjacent_ea_ids"] = {1}

        run_phase_8(self.alg, {}, None, self.feedback, None, p1, p2, p3, p4, p7)

        self.assertEqual(len(bldg_sink.features), 1)
        feat = bldg_sink.features[0]
        self.assertEqual(feat.attribute("parent_ean"), "002000")
        self.assertEqual(
            feat.attribute("merge_role"),
            "Delineation Candidate",
            "Delineation Candidate must take precedence over Merge Partner to prevent QGIS filter exclusion."
        )


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

    def test_phase8_extracts_buildings_for_candidate_with_proposed_split_cut_line(self):
        """Verify that an over-threshold EA with has_proposed_split=True (from_split=False) has buildings extracted."""
        p1, p2, p3, p4, p7, bldg_sink = self._setup_pipeline_fixtures(exec_mode="delineation")

        # Configure EA 020000 with 349 HH and proposed split cut line (un-split whole polygon)
        poly = QgsGeometry.fromPolygonXY([[QgsPointXY(20, 20), QgsPointXY(25, 20), QgsPointXY(25, 25), QgsPointXY(20, 25), QgsPointXY(20, 20)]])
        bldg_pt = {
            "point": QgsPointXY(22.0, 22.0),
            "pop": 349.0,
            "bldgpoints_value": 1.0,
            "attributes": [99, 999, 1.0, 349.0],
            "parent_ean": "020000",
        }
        ea_cand = {
            "original_id": 99,
            "original_code": "020000",
            "new_ea_code": "020000",
            "parent_barangay": "01101003",
            "geom": poly,
            "buildings": [bldg_pt],
            "hh_count": 349,
            "original_hhcount": 349,
            "bldg_count": 1,
            "has_proposed_split": True,
            "from_split": False,
            "from_merge": False,
        }
        p7["eas"] = [ea_cand]
        p2["delineation_candidate_ids"] = {99}

        run_phase_8(self.alg, {}, None, self.feedback, None, p1, p2, p3, p4, p7)

        self.assertEqual(len(bldg_sink.features), 1, "Candidate EA with proposed split must have its buildings extracted.")
        feat = bldg_sink.features[0]
        self.assertEqual(feat.attribute("parent_ean"), "020000")
        self.assertEqual(feat.attribute("candidate_ean"), "020000")
        self.assertEqual(feat.attribute("merge_role"), "Delineation Candidate")

    def test_phase8_fallback_queries_building_source_when_ea_buildings_empty(self):
        """Verify fallback to direct building_source spatial query when ea.get('buildings') is empty."""
        p1, p2, p3, p4, p7, bldg_sink = self._setup_pipeline_fixtures(exec_mode="delineation")

        # EA 020000 with empty buildings list
        poly = QgsGeometry.fromPolygonXY([[QgsPointXY(30, 30), QgsPointXY(35, 30), QgsPointXY(35, 35), QgsPointXY(30, 35), QgsPointXY(30, 30)]])
        ea_cand = {
            "original_id": 100,
            "original_code": "020000",
            "new_ea_code": "020000",
            "parent_barangay": "01101003",
            "geom": poly,
            "buildings": [],  # Empty
            "hh_count": 349,
            "original_hhcount": 349,
            "bldg_count": 0,
            "has_proposed_split": True,
            "from_split": False,
            "from_merge": False,
        }
        p7["eas"] = [ea_cand]
        p2["delineation_candidate_ids"] = {100}

        # Add building point directly into building_source
        bldg_layer = p1["building_source"]
        feat = QgsFeature(bldg_layer.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(32.0, 32.0)))
        feat.setAttributes([501, 5001, 1.0, 5.0])
        bldg_layer.dataProvider().addFeatures([feat])
        bldg_layer.updateExtents()

        run_phase_8(self.alg, {}, None, self.feedback, None, p1, p2, p3, p4, p7)

        self.assertGreaterEqual(len(bldg_sink.features), 1, "Fallback query must extract building point from building_source.")
        feat_out = bldg_sink.features[0]
        self.assertEqual(feat_out.attribute("parent_ean"), "020000")
        self.assertEqual(feat_out.attribute("candidate_ean"), "020000")
        self.assertEqual(feat_out.attribute("merge_role"), "Delineation Candidate")

    def test_phase8_strictly_excludes_buildings_outside_candidate_polygon_in_delineation_mode(self):
        """Verify that building points positioned outside candidate polygon boundaries are not extracted."""
        p1, p2, p3, p4, p7, bldg_sink = self._setup_pipeline_fixtures(exec_mode="delineation")

        # Candidate EA with polygon bounds [0, 0] to [5, 5]
        poly = QgsGeometry.fromPolygonXY([[QgsPointXY(0, 0), QgsPointXY(5, 0), QgsPointXY(5, 5), QgsPointXY(0, 5), QgsPointXY(0, 0)]])
        
        # Point 1: Inside the candidate polygon (x=2, y=2)
        bldg_inside = {
            "point": QgsPointXY(2.0, 2.0),
            "pop": 350.0,
            "bldgpoints_value": 1.0,
            "attributes": [1, 101, 1.0, 350.0],
            "parent_ean": "002000",
        }
        # Point 2: Outside the candidate polygon (x=50, y=50)
        bldg_outside = {
            "point": QgsPointXY(50.0, 50.0),
            "pop": 10.0,
            "bldgpoints_value": 1.0,
            "attributes": [2, 102, 1.0, 10.0],
            "parent_ean": "002000",
        }

        ea_cand = {
            "original_id": 1,
            "original_code": "002000",
            "new_ea_code": "002000",
            "parent_barangay": "01101003",
            "geom": poly,
            "buildings": [bldg_inside, bldg_outside],
            "hh_count": 360,
            "original_hhcount": 360,
            "bldg_count": 2,
            "from_split": False,
            "from_merge": False,
        }
        p7["eas"] = [ea_cand]
        p2["delineation_candidate_ids"] = {1}

        run_phase_8(self.alg, {}, None, self.feedback, None, p1, p2, p3, p4, p7)

        # Only the point inside the polygon must be extracted
        self.assertEqual(len(bldg_sink.features), 1, "Only points inside the candidate polygon should be extracted.")
        feat = bldg_sink.features[0]
        self.assertEqual(feat.geometry().asPoint().x(), 2.0)
        self.assertEqual(feat.geometry().asPoint().y(), 2.0)

    def test_dialog_subset_string_whitelists_delineation_roles(self):
        """Verify dialog applies strict subset string whitelisting Delineation Candidate and Delineated roles."""
        import inspect
        from references.create_enumeration_area.dialog import EALauncherDialog

        src = inspect.getsource(EALauncherDialog.run_pipeline)
        self.assertIn("layer.setSubsetString('\"merge_role\" IN (\\'Delineation Candidate\\', \\'Delineated\\')')", src)

    def test_phase4_does_not_load_merge_candidates_in_delineation_mode(self):
        """Verify run_phase_4 does not add merge candidates or contiguous partners to needed_ea_ids in delineation mode."""
        from references.create_enumeration_area.phases.phase4_load_eas import run_phase_4
        from qgis.core import QgsProcessingMultiStepFeedback

        export_field_names = ["fid", "geocode", "ean", "hhcount"]
        fields = QgsFields()
        for fname in export_field_names:
            fields.append(QgsField(fname, QVariant.Int if fname == "fid" else QVariant.String))

        # EA 1: Delineation Candidate
        f1 = QgsFeature(fields)
        f1.setId(1)
        f1.setAttributes([1, "01101003", "002000", "350"])
        f1.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(0, 0), QgsPointXY(5, 0), QgsPointXY(5, 5), QgsPointXY(0, 5), QgsPointXY(0, 0)]]))

        # EA 2: Merge Candidate (touching EA 3)
        f2 = QgsFeature(fields)
        f2.setId(2)
        f2.setAttributes([2, "01101003", "001000", "80"])
        f2.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(5, 0), QgsPointXY(10, 0), QgsPointXY(10, 5), QgsPointXY(5, 5), QgsPointXY(5, 0)]]))

        # EA 3: Neighbor EA
        f3 = QgsFeature(fields)
        f3.setId(3)
        f3.setAttributes([3, "01101003", "003000", "200"])
        f3.setGeometry(QgsGeometry.fromPolygonXY([[QgsPointXY(10, 0), QgsPointXY(15, 0), QgsPointXY(15, 5), QgsPointXY(10, 5), QgsPointXY(10, 0)]]))

        ea_layer = QgsVectorLayer("Polygon?crs=EPSG:4326", "test_ea", "memory")
        for i in range(fields.count()):
            ea_layer.dataProvider().addAttributes([fields.at(i)])
        ea_layer.updateFields()
        ea_layer.dataProvider().addFeatures([f1, f2, f3])
        ea_layer.updateExtents()

        p1 = {
            "all_ea_features": [f1, f2, f3],
            "previous_ea_source": ea_layer,
            "household_field": "hhcount",
            "ea_id_field": "ean",
            "gap_source": None,
            "overlap_source": None,
            "special_ea_info": {},
            "special_ea_ids": set(),
            "min_household": 150,
            "max_household": 300,
            "barangay_index": QgsSpatialIndex(),
            "barangay_by_id": {},
            "_dc_geo_idx": 1,
            "barangay_id_field": "geocode",
            "execution_mode": "delineation",
        }
        p2 = {
            "delineation_candidate_ids": {1},
            "merge_candidate_ids": {2},
            "ea_id_to_buildings": {},
            "imputed_hhcount": {},
        }

        multi_feedback = QgsProcessingMultiStepFeedback(8, self.feedback)
        res = run_phase_4(self.alg, {}, None, self.feedback, multi_feedback, p1, p2, 3)

        self.assertIn(1, res["needed_ea_ids"], "Delineation candidate EA 1 must be loaded in delineation mode.")
        self.assertNotIn(2, res["needed_ea_ids"], "Merge candidate EA 2 must NOT be loaded in delineation mode.")
        self.assertNotIn(3, res["needed_ea_ids"], "Neighbor EA 3 must NOT be loaded in delineation mode.")

    def test_delineation_mode_drops_buildings_outside_candidate_polygon(self):
        """Verify that points outside delineation candidate polygons are strictly dropped."""
        p1, p2, p3, p4, p7, bldg_sink = self._setup_pipeline_fixtures(exec_mode="delineation")

        # Candidate polygon EA 1 is from (0,0) to (5,5)
        # Add building inside (2,2) and building outside (12,12) to ea_delin
        bldg_inside = {
            'point': QgsPointXY(2.0, 2.0),
            'pop': 1.0,
            'bldgpoints_value': 1.0,
            'attributes': [1, 101, 1.0, 1.0],
            'parent_ean': "002000",
            'merge_role': "Delineation Candidate",
            'candidate_ean': "002000",
        }
        bldg_outside = {
            'point': QgsPointXY(12.0, 12.0),  # strictly outside candidate polygon!
            'pop': 1.0,
            'bldgpoints_value': 1.0,
            'attributes': [2, 102, 1.0, 1.0],
            'parent_ean': "002000",
            'merge_role': "Delineation Candidate",
            'candidate_ean': "002000",
        }
        p7["eas"][0]["buildings"] = [bldg_inside, bldg_outside]

        # Also register EA 1 in all_ea_features so full_ea_by_id has its geometry
        feat_ea1 = QgsFeature()
        feat_ea1.setId(1)
        feat_ea1.setGeometry(p7["eas"][0]["geom"])
        p1["all_ea_features"] = [feat_ea1]

        run_phase_8(self.alg, {}, None, self.feedback, None, p1, p2, p3, p4, p7)

        # Only 1 building feature should be written (the one inside candidate)
        self.assertEqual(len(bldg_sink.features), 1, "Only building inside candidate polygon must be written.")
        written_geom = bldg_sink.features[0].geometry().asPoint()
        self.assertAlmostEqual(written_geom.x(), 2.0, places=4)
        self.assertAlmostEqual(written_geom.y(), 2.0, places=4)

    def test_dialog_executes_native_extract_by_location(self):
        """Verify dialog.run_pipeline invokes native:extractbylocation using delineation candidates as reference."""
        import inspect
        from references.create_enumeration_area.dialog import EALauncherDialog

        src = inspect.getsource(EALauncherDialog.run_pipeline)
        self.assertIn('"native:extractbylocation"', src, "Dialog must invoke native:extractbylocation.")
        self.assertIn("'INTERSECT': delin_cand_lyr", src, "Dialog must pass delin_cand_lyr as INTERSECT layer.")
        self.assertIn("'INPUT': bldg_layer", src, "Dialog must pass bldg_layer as INPUT.")

    def test_phase8_implements_native_extract_by_location(self):
        """Verify phase8_output implements native:extractbylocation using candidate polygons as reference."""
        import inspect
        from references.create_enumeration_area.phases.phase8_output import run_phase_8

        src = inspect.getsource(run_phase_8)
        self.assertIn('"native:extractbylocation"', src, "phase8_output must invoke native:extractbylocation.")
        self.assertIn("'INTERSECT': cand_ref_lyr", src, "phase8_output must pass cand_ref_lyr as INTERSECT reference.")


if __name__ == "__main__":
    unittest.main()


