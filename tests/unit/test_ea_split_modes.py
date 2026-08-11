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
        parts = [
            {'geom': p1, 'hh_count': 120.0},
            {'geom': p2, 'hh_count': 130.0},
        ]
        allocated = allocate_gaps_to_parts(parts, parent)
        self.assertEqual(len(allocated), 2)


if __name__ == "__main__":
    unittest.main()
