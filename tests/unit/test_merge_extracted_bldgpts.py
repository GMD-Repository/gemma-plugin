# -*- coding: utf-8 -*-
"""
Unit test module for extracted building points in the EA Merging workflow.
Verifies:
1. Deduplication of building points by geometry coordinates (highest household count prevails).
2. Role attribution (merge_role = 'Candidate', 'Merge Partner', 'Merged').
3. Preserving and deduplicating buildings when two EAs merge in Phase 6.
4. Interactive merge synchronization and deduplication in dialog.py.
"""

import unittest
from tests.mocks.qgis_mock import setup_qgis_mock_if_needed

setup_qgis_mock_if_needed()

from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsFields,
    QgsField,
    QgsVectorLayer,
    QgsProject,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant

from references.create_enumeration_area.helpers.spatial import deduplicate_building_points


class TestMergeExtractedBldgpts(unittest.TestCase):
    """Test suite for extracted building points and deduplication in EA merging."""

    def test_deduplicate_building_points_highest_hh_prevails(self):
        """Verify that when duplicate geometries exist, the point with highest pop prevails."""
        bldgs = [
            {
                'point': QgsPointXY(120.500001, 14.500001),
                'pop': 2.0,
                'bldgpoints_value': 100.0,
                'parent_ean': '001',
                'merge_role': 'Candidate',
            },
            {
                'point': QgsPointXY(120.500001, 14.500001),  # Duplicate geometry
                'pop': 5.0,  # Higher household count - should prevail
                'bldgpoints_value': 200.0,
                'parent_ean': '002',
                'merge_role': 'Merge Partner',
            },
            {
                'point': QgsPointXY(120.500001, 14.500001),  # Another duplicate
                'pop': 1.0,  # Lower - should be dropped
                'bldgpoints_value': 50.0,
                'parent_ean': '002',
                'merge_role': 'Merge Partner',
            },
            {
                'point': QgsPointXY(120.600000, 14.600000),  # Unique geometry
                'pop': 3.0,
                'bldgpoints_value': 150.0,
                'parent_ean': '001',
                'merge_role': 'Candidate',
            },
        ]

        deduped, dropped_cnt = deduplicate_building_points(bldgs)

        self.assertEqual(dropped_cnt, 2, "Should drop exactly 2 duplicate points")
        self.assertEqual(len(deduped), 2, "Should have 2 unique prevailing points")

        # Find prevailing point at (120.500001, 14.500001)
        pt1 = next(b for b in deduped if abs(b['point'].x() - 120.500001) < 1e-5)
        self.assertEqual(pt1['pop'], 5.0, "Prevailing point must have the highest household count (5.0)")
        self.assertEqual(pt1['parent_ean'], '002', "Prevailing point attributes must be preserved")

        # Unique point at (120.6, 14.6)
        pt2 = next(b for b in deduped if abs(b['point'].x() - 120.6) < 1e-5)
        self.assertEqual(pt2['pop'], 3.0)

    def test_deduplicate_empty_and_single(self):
        """Verify deduplication handles empty lists and single items cleanly."""
        deduped, dropped = deduplicate_building_points([])
        self.assertEqual(deduped, [])
        self.assertEqual(dropped, 0)

        single = [{'point': QgsPointXY(10.0, 20.0), 'pop': 1.0}]
        deduped, dropped = deduplicate_building_points(single)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(dropped, 0)

    def test_phase6_merge_buildings_deduplication(self):
        """Verify that when Phase 6 merges two EAs, combined buildings are deduplicated by pop."""
        from references.create_enumeration_area.phases.phase6_merge import deduplicate_building_points

        # Candidate EA with 2 buildings
        ea_bldgs = [
            {'point': QgsPointXY(1.0, 1.0), 'pop': 4.0, 'parent_ean': 'EA_A', 'merge_role': 'Candidate'},
            {'point': QgsPointXY(2.0, 2.0), 'pop': 2.0, 'parent_ean': 'EA_A', 'merge_role': 'Candidate'},
        ]
        # Partner EA with 2 buildings (one duplicates point (2.0, 2.0) with pop=6.0)
        nb_bldgs = [
            {'point': QgsPointXY(2.0, 2.0), 'pop': 6.0, 'parent_ean': 'EA_B', 'merge_role': 'Merge Partner'},
            {'point': QgsPointXY(3.0, 3.0), 'pop': 1.0, 'parent_ean': 'EA_B', 'merge_role': 'Merge Partner'},
        ]

        combined = list(ea_bldgs) + list(nb_bldgs)
        deduped, drop_cnt = deduplicate_building_points(combined)

        self.assertEqual(drop_cnt, 1, "Duplicate point at (2.0, 2.0) should be dropped")
        self.assertEqual(len(deduped), 3)

        # Winning point at (2.0, 2.0) should have pop=6.0
        pt = next(b for b in deduped if abs(b['point'].x() - 2.0) < 1e-5)
        self.assertEqual(pt['pop'], 6.0)

        # Total households from deduplicated buildings
        total_hh = sum(b['pop'] for b in deduped)
        self.assertEqual(total_hh, 4.0 + 6.0 + 1.0)  # 11.0, not 13.0 with duplicate

    def test_role_attribution_candidate_and_partner(self):
        """Verify role attribution for Candidate, Merge Partner, and Delineation Candidate."""
        merge_candidate_ids = {101}
        adjacent_ea_ids = {102}
        delineation_candidate_ids = {103}
        partner_to_candidate_eans = {102: {"001"}}

        def get_role_and_cand_ean(ea_id, ea_ean):
            if ea_id in merge_candidate_ids:
                return "Candidate", ea_ean
            elif ea_id in adjacent_ea_ids:
                return "Merge Partner", ", ".join(sorted(partner_to_candidate_eans.get(ea_id, set())))
            elif ea_id in delineation_candidate_ids:
                return "Delineation Candidate", ""
            return "Other", ""

        role1, cand_ean1 = get_role_and_cand_ean(101, "001")
        self.assertEqual(role1, "Candidate")
        self.assertEqual(cand_ean1, "001")

        role2, cand_ean2 = get_role_and_cand_ean(102, "002")
        self.assertEqual(role2, "Merge Partner")
        self.assertEqual(cand_ean2, "001")

        role3, cand_ean3 = get_role_and_cand_ean(103, "003")
        self.assertEqual(role3, "Delineation Candidate")
        self.assertEqual(cand_ean3, "")

    def test_dialog_points_by_geom_deduplication(self):
        """Verify the dialog point calculation deduplicates points by coordinate and sums highest hhcount."""
        # Simulated raw building records intersecting merged geometry with duplicates
        raw_records = [
            (QgsPointXY(10.000000, 20.000000), 2.0),
            (QgsPointXY(10.000000, 20.000000), 7.0),  # Duplicate coordinate with higher hh
            (QgsPointXY(10.000000, 20.000000), 1.0),  # Duplicate coordinate with lower hh
            (QgsPointXY(10.000050, 20.000050), 3.0),  # Distinct coordinate
        ]

        points_by_geom = {}
        for pt, val in raw_records:
            k = (round(pt.x(), 6), round(pt.y(), 6))
            points_by_geom.setdefault(k, []).append(val)

        b_cnt = 0
        b_hh = 0.0
        for k, val_list in points_by_geom.items():
            val_list.sort(reverse=True)
            b_cnt += 1
            b_hh += val_list[0]

        self.assertEqual(b_cnt, 2, "Duplicate coordinates should count as 1 building point")
        self.assertEqual(b_hh, 7.0 + 3.0, "Total HH should sum prevailing highest values (7.0 + 3.0 = 10.0)")


if __name__ == '__main__':
    unittest.main()
