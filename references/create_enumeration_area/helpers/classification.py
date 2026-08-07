from typing import Dict, Any, Set, Optional
from qgis.core import QgsFeature

def get_classification_count(ea_item: Dict[str, Any]) -> float:
    """Return household count for classification decisions."""
    return ea_item['hh_count']


def is_parent_delineation_candidate(
    ea_item: Dict[str, Any],
    eadel_indi_col_idx: int,
    full_ea_by_id: Dict[int, QgsFeature]
) -> bool:
    """Check if EA item is explicitly designated for delineation via attribute field."""
    orig_id = ea_item.get('original_id')
    if orig_id is not None and eadel_indi_col_idx != -1 and orig_id in full_ea_by_id:
        val = full_ea_by_id[orig_id].attribute(eadel_indi_col_idx)
        return val is not None and str(val).strip().lower() in ("for delineation", "for_delineation")
    return False


def is_delineation_candidate(
    ea_item: Dict[str, Any],
    max_household: float,
    eadel_indi_col_idx: int,
    full_ea_by_id: Dict[int, QgsFeature],
    delineation_candidate_ids: Set[int]
) -> bool:
    """Check if EA item is a candidate for delineation."""
    if ea_item.get('from_split', False) or ea_item.get('from_merge', False):
        return False
    orig_id = ea_item.get('original_id')
    is_explicit = False
    if eadel_indi_col_idx != -1 and orig_id in full_ea_by_id:
        val = full_ea_by_id[orig_id].attribute(eadel_indi_col_idx)
        is_explicit = (val is not None and str(val).strip().lower() in ("for delineation", "for_delineation"))
    return is_explicit or (orig_id in delineation_candidate_ids) or (ea_item['hh_count'] >= max_household)


def is_merge_candidate(
    ea_item: Dict[str, Any],
    min_household: float,
    merge_candidate_ids: Set[int]
) -> bool:
    """Check if EA item is a candidate for merging."""
    if ea_item.get('from_split', False):
        return ea_item['hh_count'] <= min_household
    if ea_item.get('from_merge', False):
        return False
    orig_id = ea_item.get('original_id')
    return (orig_id in merge_candidate_ids) or (ea_item['hh_count'] <= min_household)
