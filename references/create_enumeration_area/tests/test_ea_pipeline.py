# -*- coding: utf-8 -*-
import unittest
from typing import Dict, Any, List

from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsPolygon,
)

from references.create_enumeration_area.helpers.classification import (
    is_delineation_candidate,
    is_merge_candidate,
)
from references.create_enumeration_area.phases.phase6_merge import (
    process_barangay_merge,
    is_delineation_candidate as phase6_is_delin,
    is_merge_candidate as phase6_is_merge,
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


def make_square_geom(x: float, y: float, size: float = 10.0) -> QgsGeometry:
    """Helper to create a square QgsGeometry centered at (x, y)."""
    p1 = QgsPointXY(x, y)
    p2 = QgsPointXY(x + size, y)
    p3 = QgsPointXY(x + size, y + size)
    p4 = QgsPointXY(x, y + size)
    return QgsGeometry.fromPolygonXY([[p1, p2, p3, p4, p1]])


class TestEAPipelineCandidateAndMerge(unittest.TestCase):

    def test_candidate_classification_predicates(self):
        """Verify strict mutual exclusivity and threshold enforcement."""
        delin_ids = set()
        merge_ids = set()

        ea_over = {"original_id": 1, "hh_count": 350.0}
        ea_exact_max = {"original_id": 2, "hh_count": 300.0}
        ea_normal = {"original_id": 3, "hh_count": 200.0}
        ea_under = {"original_id": 4, "hh_count": 50.0}

        # 1. Over-threshold / Max threshold (>= 300)
        self.assertTrue(is_delineation_candidate(ea_over, max_household=300, eadel_indi_col_idx=-1, full_ea_by_id={}, delineation_candidate_ids=delin_ids))
        self.assertTrue(is_delineation_candidate(ea_exact_max, max_household=300, eadel_indi_col_idx=-1, full_ea_by_id={}, delineation_candidate_ids=delin_ids))
        self.assertFalse(is_delineation_candidate(ea_normal, max_household=300, eadel_indi_col_idx=-1, full_ea_by_id={}, delineation_candidate_ids=delin_ids))
        self.assertFalse(is_delineation_candidate(ea_under, max_household=300, eadel_indi_col_idx=-1, full_ea_by_id={}, delineation_candidate_ids=delin_ids))

        # 2. Under-threshold (<= 100)
        self.assertTrue(is_merge_candidate(ea_under, min_household=100, merge_candidate_ids=merge_ids))
        self.assertFalse(is_merge_candidate(ea_normal, min_household=100, merge_candidate_ids=merge_ids))
        self.assertFalse(is_merge_candidate(ea_over, min_household=100, merge_candidate_ids=merge_ids))

    def test_merge_all_under_threshold_candidates(self):
        """Verify that multiple adjacent under-threshold EAs successfully merge together when no reference EA exists."""
        feedback = MockFeedback()

        geom1 = make_square_geom(0, 0, 10)
        geom2 = make_square_geom(10, 0, 10)  # adjacent to geom1

        ea1 = {
            'geom': geom1,
            'buildings': [],
            'hh_count': 40.0,
            'original_hhcount': 40.0,
            'bldg_count': 2,
            'attributes': [1, "EA 001"],
            'original_id': 101,
            'original_code': "01737001001",
            'is_new': False,
            'split_by': 'none',
            'from_merge': False,
            'from_split': False,
            'parent_barangay': "01737"
        }

        ea2 = {
            'geom': geom2,
            'buildings': [],
            'hh_count': 50.0,
            'original_hhcount': 50.0,
            'bldg_count': 3,
            'attributes': [2, "EA 002"],
            'original_id': 102,
            'original_code': "01737001002",
            'is_new': False,
            'split_by': 'none',
            'from_merge': False,
            'from_split': False,
            'parent_barangay': "01737"
        }

        merged = process_barangay_merge(
            bar_code="01737",
            bar_eas=[ea1, ea2],
            fback=feedback,
            min_household=100.0,
            max_household=300.0,
            merge_candidate_ids={101, 102}
        )

        self.assertEqual(len(merged), 1, "The 2 adjacent under-threshold candidates must merge into 1 EA.")
        self.assertEqual(merged[0]['hh_count'], 90.0, "Combined household count should be 40 + 50 = 90 HH.")
        self.assertTrue(merged[0].get('from_merge', False), "Output EA must be flagged with from_merge=True.")

    def test_merge_candidate_with_normal_reference_ea(self):
        """Verify that an under-threshold candidate prefers merging with a normal reference EA if present."""
        feedback = MockFeedback()

        geom1 = make_square_geom(0, 0, 10)
        geom2 = make_square_geom(10, 0, 10)

        ea_small = {
            'geom': geom1,
            'buildings': [],
            'hh_count': 40.0,
            'original_hhcount': 40.0,
            'bldg_count': 1,
            'attributes': [1, "EA 001"],
            'original_id': 201,
            'original_code': "01737002001",
            'is_new': False,
            'from_merge': False,
            'from_split': False,
            'parent_barangay': "01737"
        }

        ea_normal = {
            'geom': geom2,
            'buildings': [],
            'hh_count': 180.0,
            'original_hhcount': 180.0,
            'bldg_count': 5,
            'attributes': [2, "EA 002"],
            'original_id': 202,
            'original_code': "01737002002",
            'is_new': False,
            'from_merge': False,
            'from_split': False,
            'parent_barangay': "01737"
        }

        merged = process_barangay_merge(
            bar_code="01737",
            bar_eas=[ea_small, ea_normal],
            fback=feedback,
            min_household=100.0,
            max_household=300.0,
            merge_candidate_ids={201}
        )

        self.assertEqual(len(merged), 1, "Small EA + normal reference EA should merge into 1 EA.")
        self.assertEqual(merged[0]['hh_count'], 220.0, "Combined household count should be 40 + 180 = 220 HH.")

    def test_prevent_merge_exceeding_max_household(self):
        """Verify that EAs are prevented from merging if their combined count exceeds max_household (300 HH)."""
        feedback = MockFeedback()

        geom1 = make_square_geom(0, 0, 10)
        geom2 = make_square_geom(10, 0, 10)

        ea1 = {
            'geom': geom1,
            'buildings': [],
            'hh_count': 200.0,
            'original_hhcount': 200.0,
            'attributes': [1, "EA 001"],
            'original_id': 301,
            'original_code': "01737003001",
            'from_merge': False,
            'from_split': False,
            'parent_barangay': "01737"
        }

        ea2 = {
            'geom': geom2,
            'buildings': [],
            'hh_count': 150.0,
            'original_hhcount': 150.0,
            'attributes': [2, "EA 002"],
            'original_id': 302,
            'original_code': "01737003002",
            'from_merge': False,
            'from_split': False,
            'parent_barangay': "01737"
        }

        # 200 + 150 = 350 > 300 max_household
        merged = process_barangay_merge(
            bar_code="01737",
            bar_eas=[ea1, ea2],
            fback=feedback,
            min_household=100.0,
            max_household=300.0,
            merge_candidate_ids={301, 302}
        )

        self.assertEqual(len(merged), 2, "EAs exceeding 300 HH when combined must NOT be merged.")

    def test_single_ea_barangay_no_merge(self):
        """Verify that an isolated single-EA barangay under min_household remains unmerged."""
        feedback = MockFeedback()
        geom = make_square_geom(0, 0, 10)
        ea = {
            'geom': geom,
            'buildings': [],
            'hh_count': 30.0,
            'original_hhcount': 30.0,
            'attributes': [1, "EA 001"],
            'original_id': 401,
            'original_code': "01737004001",
            'from_merge': False,
            'from_split': False,
            'parent_barangay': "01737004"
        }

        merged = process_barangay_merge("01737004", [ea], feedback, min_household=100.0, max_household=300.0)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]['hh_count'], 30.0)

    def test_disallow_candidate_merge_setting(self):
        """Verify that setting allow_candidate_merge=False prevents candidate-to-candidate merging."""
        feedback = MockFeedback()

        geom1 = make_square_geom(0, 0, 10)
        geom2 = make_square_geom(10, 0, 10)

        ea1 = {
            'geom': geom1,
            'buildings': [],
            'hh_count': 40.0,
            'original_hhcount': 40.0,
            'attributes': [1, "EA 001"],
            'original_id': 501,
            'original_code': "01737005001",
            'from_merge': False,
            'from_split': False,
            'parent_barangay': "01737005"
        }
        ea2 = {
            'geom': geom2,
            'buildings': [],
            'hh_count': 50.0,
            'original_hhcount': 50.0,
            'attributes': [2, "EA 002"],
            'original_id': 502,
            'original_code': "01737005002",
            'from_merge': False,
            'from_split': False,
            'parent_barangay': "01737005"
        }

        # With allow_candidate_merge=False, candidate EAs should NOT merge together
        merged = process_barangay_merge(
            bar_code="01737005",
            bar_eas=[ea1, ea2],
            fback=feedback,
            min_household=100.0,
            max_household=300.0,
            merge_candidate_ids={501, 502},
            allow_candidate_merge=False
        )

        self.assertEqual(len(merged), 2, "When allow_candidate_merge=False, small candidates must NOT merge together.")


if __name__ == "__main__":
    unittest.main()
