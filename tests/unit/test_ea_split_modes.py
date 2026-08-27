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


if __name__ == "__main__":
    unittest.main()

