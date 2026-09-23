# -*- coding: utf-8 -*-
import unittest
from typing import Dict, Any, List

from tests.mocks.qgis_mock import setup_qgis_mock_if_needed
setup_qgis_mock_if_needed()

from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
)

from references.create_enumeration_area.helpers.geometry import (
    get_polylines_from_geom,
    get_polygons_from_geom,
    allocate_gaps_to_parts,
)
from references.create_enumeration_area.phases.phase5_delineate import (
    force_geometric_split,
)


class MockFeedback:
    def isCanceled(self):
        return False

    def pushInfo(self, msg):
        pass

    def pushWarning(self, msg):
        pass

    def reportError(self, msg):
        pass

    def setCurrentStep(self, s):
        pass

    def setProgressText(self, t):
        pass

    def setProgress(self, p):
        pass


def make_square_geom(x: float, y: float, size: float = 100.0) -> QgsGeometry:
    p1 = QgsPointXY(x, y)
    p2 = QgsPointXY(x + size, y)
    p3 = QgsPointXY(x + size, y + size)
    p4 = QgsPointXY(x, y + size)
    return QgsGeometry.fromPolygonXY([[p1, p2, p3, p4, p1]])


class TestEASplitModes(unittest.TestCase):

    def test_get_polylines_from_geom(self):
        p1 = QgsPointXY(0, 0)
        p2 = QgsPointXY(100, 100)
        line_geom = QgsGeometry.fromPolylineXY([p1, p2])
        polylines = get_polylines_from_geom(line_geom)
        self.assertGreaterEqual(len(polylines), 1)
        self.assertEqual(len(polylines[0]), 2)

    def test_force_geometric_split_fallback(self):
        """Verify that force_geometric_split produces strip cuts when invoked as last resort."""
        feedback = MockFeedback()
        geom = make_square_geom(0, 0, 100)
        bldgs = [
            {'point': QgsPointXY(25, 25), 'pop': 150.0},
            {'point': QgsPointXY(75, 75), 'pop': 200.0},
        ]
        ea = {
            'geom': geom,
            'buildings': bldgs,
            'hh_count': 350.0,
            'original_hhcount': 350.0,
            'bldg_count': 2,
            'attributes': [1, "EA 001"],
            'original_id': 1001,
            'original_code': "01716001001",
            'is_new': False,
            'from_split': False,
            'split_by': 'none',
            'parent_barangay': "01716"
        }

        parts = force_geometric_split(ea, target_pop=200, fback=feedback, min_household=100, max_household=300)
        self.assertGreaterEqual(len(parts), 2, "Force geometric split should produce >= 2 parts.")
        for p in parts:
            self.assertEqual(p['split_by'], 'forced_grid')

    def test_allocate_gaps_to_parts(self):
        """Verify gap allocation helper."""
        parent = make_square_geom(0, 0, 100)
        p1 = make_square_geom(0, 0, 50)
        p2 = make_square_geom(50, 0, 50)
    def test_assign_buildings_to_parts_exact_hh_preservation(self):
        """Verify that assign_buildings_to_parts preserves 100% of buildings with zero duplicates and zero loss."""
        from references.create_enumeration_area.helpers.geometry import assign_buildings_to_parts
        feedback = MockFeedback()
        
        # Two adjacent polygons: [0, 50] and [50, 100]
        p1 = make_square_geom(0, 0, 50)
        p2 = make_square_geom(50, 0, 50)
        part_geoms = [p1, p2]
        
        # Test 1: Buildings clearly inside p1 and p2
        # Test 2: Building exactly on the shared boundary (x=50)
        # Test 3: Orphan building slightly outside in a gap (x=110)
        bldgs = [
            {'point': QgsPointXY(20, 20), 'pop': 100.0, 'id': 1},
            {'point': QgsPointXY(50, 25), 'pop': 50.0, 'id': 2},  # on boundary
            {'point': QgsPointXY(80, 80), 'pop': 150.0, 'id': 3},
            {'point': QgsPointXY(110, 50), 'pop': 9.0, 'id': 4},  # outside/orphan
        ]
        
        assigned = assign_buildings_to_parts(bldgs, part_geoms, feedback, "EA_TEST")
        self.assertEqual(len(assigned), 2)
        
        # Verify total buildings assigned equals total input buildings
        total_assigned_bldgs = sum(len(part) for part in assigned)
        self.assertEqual(total_assigned_bldgs, len(bldgs))
        
        # Verify total HH sum is 100% exact (100 + 50 + 150 + 9 = 309)
        total_pop = sum(sum(b['pop'] for b in part) for part in assigned)
        self.assertEqual(total_pop, 309.0)
        
        # Verify no building is duplicated across parts
        all_ids = [b['id'] for part in assigned for b in part]
        self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_split_ea_voronoi_road_hybrid_preserves_hh(self):
        """Verify that split_ea_voronoi_road_hybrid produces exact HH conservation."""
        from references.create_enumeration_area.phases.phase5_delineate import split_ea_voronoi_road_hybrid
        feedback = MockFeedback()
        geom = make_square_geom(0, 0, 100)
        
        bldgs = [
            {'point': QgsPointXY(20, 20), 'pop': 150.0},
            {'point': QgsPointXY(80, 80), 'pop': 159.0},
        ]
        ea = {
            'geom': geom,
            'buildings': bldgs,
            'hh_count': 309.0,
            'original_hhcount': 309.0,
            'bldg_count': 2,
            'attributes': [1, "EA 001"],
            'original_id': 1001,
            'original_code': "01716001001",
            'is_new': False,
            'from_split': False,
            'split_by': 'none',
            'parent_barangay': "01716"
        }
        
        road_line = QgsGeometry.fromPolylineXY([QgsPointXY(50, -10), QgsPointXY(50, 110)])
        parts = split_ea_voronoi_road_hybrid(ea, [road_line], [], target_pop=200, fback=feedback)
        
        self.assertGreaterEqual(len(parts), 2)
        total_result_hh = sum(p['hh_count'] for p in parts)
        self.assertEqual(total_result_hh, 309.0, "Resulting sub-EAs must preserve exact HH count (309).")

    def test_verify_point_cluster_alignment_small_area(self):
        """Verify point cluster alignment and threshold enforcement for clustered points in small areas."""
        from references.create_enumeration_area.phases.phase5_delineate import (
            verify_point_cluster_alignment,
            split_ea_voronoi_road_hybrid,
        )
        feedback = MockFeedback()

        # Clustered points in a small 50x50m area along diagonal
        bldgs = [
            {'point': QgsPointXY(10.0, 10.0), 'pop': 120.0},
            {'point': QgsPointXY(20.0, 20.0), 'pop': 110.0},
            {'point': QgsPointXY(30.0, 30.0), 'pop': 130.0},
        ]
        parent_geom = make_square_geom(0, 0, 50)

        # 1. Test verify_point_cluster_alignment computes valid aligned centroids
        aligned = verify_point_cluster_alignment(bldgs, parent_geom.boundingBox(), target_pop=180, k_val=2)
        self.assertEqual(len(aligned), 2, "Point cluster alignment should yield k_val aligned centroids.")

        # 2. Test split_ea_voronoi_road_hybrid on clustered points in small area with splitting line
        ea = {
            'geom': parent_geom,
            'buildings': bldgs,
            'hh_count': 360.0,
            'original_hhcount': 360.0,
            'bldg_count': 3,
            'attributes': [1, "EA 002"],
            'original_id': 1002,
            'original_code': "01716001002",
            'is_new': False,
            'from_split': False,
            'split_by': 'none',
            'parent_barangay': "01716"
        }

        road_line = QgsGeometry.fromPolylineXY([QgsPointXY(25, -10), QgsPointXY(25, 60)])
        parts = split_ea_voronoi_road_hybrid(ea, [road_line], [], target_pop=180, fback=feedback, min_household=100, max_household=300)
        self.assertGreaterEqual(len(parts), 2, "Clustered points delineation in small area should split EA into >= 2 parts.")
        for p in parts:
            self.assertGreaterEqual(p['hh_count'], 100.0, f"Resulting EA ({p['hh_count']} HH) must not fall below min threshold (100).")
            self.assertLessEqual(p['hh_count'], 300.0, f"Resulting EA ({p['hh_count']} HH) must not increase above max threshold (300).")

    def test_split_polygon_by_linear_features_direct_road_cut(self):
        """Verify that split_polygon_by_linear_features cleanly cuts an EA polygon along a road."""
        from references.create_enumeration_area.phases.phase5_delineate import split_polygon_by_linear_features
        feedback = MockFeedback()
        geom = make_square_geom(0, 0, 100)
        bldgs = [
            {'point': QgsPointXY(20, 50), 'pop': 140.0},
            {'point': QgsPointXY(80, 50), 'pop': 180.0},
        ]
        ea = {
            'geom': geom,
            'buildings': bldgs,
            'hh_count': 320.0,
            'original_hhcount': 320.0,
            'bldg_count': 2,
            'attributes': [1, "EA 001"],
            'original_id': 1001,
            'original_code': "01716001001",
            'is_new': False,
            'from_split': False,
            'split_by': 'none',
            'parent_barangay': "01716"
        }
        road_line = QgsGeometry.fromPolylineXY([QgsPointXY(50, -10), QgsPointXY(50, 110)])
        parts = split_polygon_by_linear_features(ea, [road_line], [], target_pop=200, fback=feedback)
        self.assertEqual(len(parts), 2, "Linear road split should produce exactly 2 parts.")
        self.assertEqual(parts[0]['split_by'], 'road')
        self.assertEqual(sum(p['hh_count'] for p in parts), 320.0)

    def test_split_polygon_by_linear_features_without_buildings(self):
        """Verify that split_polygon_by_linear_features cuts along a road even without building points."""
        from references.create_enumeration_area.phases.phase5_delineate import split_polygon_by_linear_features
        feedback = MockFeedback()
        geom = make_square_geom(0, 0, 100)
        ea = {
            'geom': geom,
            'buildings': [],
            'hh_count': 250.0,
            'original_hhcount': 250.0,
            'bldg_count': 0,
            'attributes': [1, "EA 001"],
            'original_id': 1001,
            'original_code': "01716001001",
            'is_new': False,
            'from_split': False,
            'split_by': 'none',
            'parent_barangay': "01716"
        }
        river_line = QgsGeometry.fromPolylineXY([QgsPointXY(-10, 50), QgsPointXY(110, 50)])
        parts = split_polygon_by_linear_features(ea, [], [river_line], target_pop=200, fback=feedback)
        self.assertEqual(len(parts), 2, "Linear river split without buildings should produce 2 parts.")
        self.assertEqual(parts[0]['split_by'], 'river')

    def test_phase5_generates_proposed_line_along_road(self):
        """Verify that run_phase_5 generates a proposed delineation cut line along a road feature."""
        from references.create_enumeration_area.phases.phase5_delineate import run_phase_5
        from qgis.core import QgsSpatialIndex

        feedback = MockFeedback()
        multi_feedback = MockFeedback()
        multi_feedback.setCurrentStep = lambda s: None
        multi_feedback.setProgressText = lambda t: None
        multi_feedback.setProgress = lambda p: None

        geom = make_square_geom(0, 0, 100)
        bldgs = [
            {'point': QgsPointXY(25, 50), 'pop': 150.0},
            {'point': QgsPointXY(75, 50), 'pop': 170.0},
        ]
        ea = {
            'geom': geom,
            'buildings': bldgs,
            'hh_count': 320.0,
            'original_hhcount': 320.0,
            'bldg_count': 2,
            'attributes': [1, "EA 001"],
            'original_id': 1001,
            'original_code': "01716001001",
            'is_new': False,
            'from_split': False,
            'split_by': 'none',
            'parent_barangay': "01716"
        }

        road_geom = QgsGeometry.fromPolylineXY([QgsPointXY(50, -10), QgsPointXY(50, 110)])
        road_index = QgsSpatialIndex()
        f_road = QgsFeature(1)
        f_road.setGeometry(road_geom)
        road_index.addFeature(f_road)
        road_geoms = {1: road_geom}

        p1 = {
            'execution_mode': 'delineation',
            'min_household': 100,
            'max_household': 300,
            'target_household': 200,
            'split_type': 0,
            'split_strategy': 0,
            'snap_tolerance': 5.0,
            'num_cores': 1,
            'barangay_index': None,
            'barangay_by_id': {},
            'special_ea_ids': set(),
            'delineation_candidate_ids': {1001},
            'all_ea_features': [],
        }
        p2 = {
            'delineation_candidate_ids': {1001},
            'merge_candidate_ids': set(),
            'delineation_candidate_hhdivthres': {},
        }
        p3 = {
            'road_index': road_index,
            'road_geoms': road_geoms,
            'river_index': None,
            'river_geoms': {},
            'ea_index': None,
            'ea_by_id': {},
        }
        p4 = {
            'eas': [ea],
        }

        res = run_phase_5(None, {}, None, feedback, multi_feedback, p1, p2, p3, p4)
        self.assertIn("proposed_lines", res)
        self.assertGreaterEqual(len(res["proposed_lines"]), 1, "Must generate proposed cut line along road.")
        prop_line = res["proposed_lines"][0]
        self.assertEqual(prop_line['split_by'], 'road')
        self.assertEqual(prop_line['ea_id'], 1001)
        # Verify parent EA is preserved whole (not pre-emptively split)
        self.assertEqual(len(res["split_eas"]), 1)
        self.assertEqual(res["split_eas"][0]['original_id'], 1001)

    def test_phase5_generates_proposed_line_along_river_subthreshold(self):
        """Verify that run_phase_5 generates a proposed cut line along river even if buildings are asymmetric."""
        from references.create_enumeration_area.phases.phase5_delineate import run_phase_5
        from qgis.core import QgsSpatialIndex

        feedback = MockFeedback()
        multi_feedback = MockFeedback()
        multi_feedback.setCurrentStep = lambda s: None
        multi_feedback.setProgressText = lambda t: None
        multi_feedback.setProgress = lambda p: None

        geom = make_square_geom(0, 0, 100)
        # All buildings on the north side of the river
        bldgs = [
            {'point': QgsPointXY(50, 75), 'pop': 320.0},
        ]
        ea = {
            'geom': geom,
            'buildings': bldgs,
            'hh_count': 320.0,
            'original_hhcount': 320.0,
            'bldg_count': 1,
            'attributes': [1, "EA 002"],
            'original_id': 1002,
            'original_code': "01716001002",
            'is_new': False,
            'from_split': False,
            'split_by': 'none',
            'parent_barangay': "01716"
        }

        river_geom = QgsGeometry.fromPolylineXY([QgsPointXY(-10, 50), QgsPointXY(110, 50)])
        river_index = QgsSpatialIndex()
        f_river = QgsFeature(1)
        f_river.setGeometry(river_geom)
        river_index.addFeature(f_river)
        river_geoms = {1: river_geom}

        p1 = {
            'execution_mode': 'delineation',
            'min_household': 100,
            'max_household': 300,
            'target_household': 200,
            'split_type': 0,
            'split_strategy': 0,
            'snap_tolerance': 5.0,
            'num_cores': 1,
            'barangay_index': None,
            'barangay_by_id': {},
            'special_ea_ids': set(),
            'delineation_candidate_ids': {1002},
            'all_ea_features': [],
        }
        p2 = {
            'delineation_candidate_ids': {1002},
            'merge_candidate_ids': set(),
            'delineation_candidate_hhdivthres': {},
        }
        p3 = {
            'road_index': None,
            'road_geoms': {},
            'river_index': river_index,
            'river_geoms': river_geoms,
            'ea_index': None,
            'ea_by_id': {},
        }
        p4 = {
            'eas': [ea],
        }

        res = run_phase_5(None, {}, None, feedback, multi_feedback, p1, p2, p3, p4)
        self.assertIn("proposed_lines", res)
        self.assertGreaterEqual(len(res["proposed_lines"]), 1, "Must generate proposed cut line along river even if asymmetric.")
        prop_line = res["proposed_lines"][0]
        self.assertEqual(prop_line['split_by'], 'river')
        self.assertEqual(prop_line['ea_id'], 1002)
        # Verify parent EA is preserved whole on map canvas
        self.assertEqual(len(res["split_eas"]), 1)
        self.assertEqual(res["split_eas"][0]['original_id'], 1002)

    def test_delineation_mode_pipeline_preserves_proposed_lines(self):
        """Verify that in delineation execution mode, Phase 6 and Phase 7 pass proposed_lines to Phase 8."""
        from references.create_enumeration_area.phases.phase5_delineate import run_phase_5
        from references.create_enumeration_area.phases.phase6_merge import run_phase_6
        from references.create_enumeration_area.phases.phase7_compliance import run_phase_7
        from references.create_enumeration_area.phases.phase8_output import run_phase_8
        from qgis.core import QgsFields, QgsField, QgsVectorLayer, QgsProject, QgsSpatialIndex, QgsCoordinateReferenceSystem
        from qgis.PyQt.QtCore import QVariant

        feedback = MockFeedback()
        multi_feedback = MockFeedback()

        parent_geom = make_square_geom(0, 0, 100)
        fields = QgsFields()
        fields.append(QgsField("geocode", QVariant.String))
        fields.append(QgsField("ean", QVariant.String))
        fields.append(QgsField("hhcount", QVariant.Double))
        fields.append(QgsField("indicator", QVariant.String))
        fields.append(QgsField("remarks", QVariant.String))

        ea_feat = QgsFeature(fields, 5001)
        ea_feat.setGeometry(parent_geom)
        ea_feat.setAttributes(["01716001", "01716001001", 350.0, "FOR DELINEATION", ""])

        ea = {
            'geom': parent_geom,
            'buildings': [
                {'point': QgsPointXY(25, 50), 'pop': 175.0},
                {'point': QgsPointXY(75, 50), 'pop': 175.0},
            ],
            'hh_count': 350.0,
            'original_hhcount': 350.0,
            'bldg_count': 2,
            'attributes': ea_feat.attributes(),
            'original_id': 5001,
            'original_code': "01716001001",
            'is_new': False,
            'from_split': False,
            'split_by': 'none',
            'parent_barangay': "01716001"
        }

        road_geom = QgsGeometry.fromPolylineXY([QgsPointXY(50, -10), QgsPointXY(50, 110)])
        f_road = QgsFeature(1)
        f_road.setGeometry(road_geom)
        road_index = QgsSpatialIndex()
        road_index.addFeature(f_road)
        road_geoms = {1: road_geom}

        crs = QgsCoordinateReferenceSystem("EPSG:4326")
        p1 = {
            'execution_mode': 'delineation',
            'eadel_indi_col_idx': -1,
            'merge_indi_col_idx': -1,
            'min_household': 100,
            'max_household': 300,
            'target_household': 200,
            'split_type': 0,
            'split_strategy': 0,
            'snap_tolerance': 15.0,
            'densify_dist': 5.0,
            'area_threshold': 100.0,
            'num_cores': 1,
            'barangay_index': None,
            'barangay_by_id': {},
            'special_ea_ids': set(),
            'delineation_candidate_ids': {5001},
            'all_ea_features': [ea_feat],
            'target_crs': crs,
            'source_crs': crs,
            'previous_ea_source': QgsVectorLayer("Polygon?crs=epsg:4326", "prev_ea", "memory"),
            'ea_id_field': 'ean',
            'bar_geocode_field': 'geocode',
            'building_source': QgsVectorLayer("Point?crs=epsg:4326", "bldg", "memory"),
            'bldg_hh_field': None,
            'out_fields': fields,
        }
        p2 = {
            'delineation_candidate_ids': {5001},
            'merge_candidate_ids': set(),
            'adjacent_ea_ids': set(),
            'delineation_candidate_hhdivthres': {5001: 0.5},
            'full_ea_by_id': {5001: ea_feat},
        }
        p3 = {
            'road_index': road_index,
            'road_geoms': road_geoms,
            'river_index': None,
            'river_geoms': {},
            'ea_index': None,
            'ea_by_id': {},
        }
        p4 = {
            'eas': [ea],
            'max_ea_number': {},
        }

        res5 = run_phase_5(None, {}, None, feedback, multi_feedback, p1, p2, p3, p4)
        self.assertEqual(len(res5.get("proposed_lines", [])), 1)

        res6 = run_phase_6(None, {}, None, feedback, multi_feedback, p1, p2, res5)
        self.assertIn("proposed_lines", res6, "Phase 6 must not drop proposed_lines in delineation mode")
        self.assertEqual(len(res6.get("proposed_lines", [])), 1)

        res7 = run_phase_7(None, {}, None, feedback, multi_feedback, p1, p2, res6)
        self.assertIn("proposed_lines", res7, "Phase 7 must preserve proposed_lines")
        self.assertEqual(len(res7.get("proposed_lines", [])), 1)

        class MockAlg:
            DELINEATED_OUTPUT = "DELINEATED_OUTPUT"
            MERGED_OUTPUT = "MERGED_OUTPUT"
            SPECIAL_EA_OUTPUT = "SPECIAL_EA_OUTPUT"
            DELINEATION_CANDIDATE_OUTPUT = "DELINEATION_CANDIDATE_OUTPUT"
            EXTRACTED_BUILDINGS_OUTPUT = "EXTRACTED_BUILDINGS_OUTPUT"

        project = QgsProject.instance()
        project.removeAllMapLayers()
        run_phase_8(MockAlg(), {}, None, feedback, multi_feedback, p1, p2, p3, p4, res7)

        layers = project.mapLayers()
        eadel_layers = [lyr for lyr in layers.values() if "eadel_update" in lyr.name()]
        self.assertEqual(len(eadel_layers), 1, "Must create eadel_update line layer")
        self.assertEqual(eadel_layers[0].featureCount(), 1, "eadel_update layer must have 1 proposed cut line")
        feat = next(eadel_layers[0].getFeatures())
        self.assertEqual(str(feat.attribute("indicator") or ""), "", "indicator in eadel_update layer must have empty/removed values")


if __name__ == "__main__":
    unittest.main()


