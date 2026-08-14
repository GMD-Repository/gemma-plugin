from typing import Optional, Dict, Any
from qgis.core import QgsFeature, QgsGeometry, QgsSpatialIndex
from PyQt5.QtCore import QVariant

def get_parent_barangay(
    ea_geom: QgsGeometry,
    barangay_index: QgsSpatialIndex,
    barangay_by_id: Dict[int, QgsFeature]
) -> Optional[QgsFeature]:
    """Find parent barangay feature by maximum area overlap."""
    candidates = barangay_index.intersects(ea_geom.boundingBox())
    max_overlap = -1.0
    parent_feat = None
    for cid in candidates:
        bar = barangay_by_id.get(cid)
        if not bar:
            continue
        bar_geom = bar.geometry()
        if bar_geom.intersects(ea_geom):
            overlap_area = bar_geom.intersection(ea_geom).area()
            if overlap_area > max_overlap:
                max_overlap = overlap_area
                parent_feat = bar
    return parent_feat


def resolve_ea_parent_barangay(
    ea_feat: QgsFeature,
    dc_geo_idx: int,
    barangay_id_field: str,
    barangay_index: QgsSpatialIndex,
    barangay_by_id: Dict[int, QgsFeature]
) -> str:
    """Resolve barangay code for an EA feature via spatial overlay (primary) or field attribute fallback."""
    # 1. Primary: Spatial overlay with Barangay Layer
    parent_feat = get_parent_barangay(ea_feat.geometry(), barangay_index, barangay_by_id)
    if parent_feat:
        val = parent_feat.attribute(barangay_id_field)
        if val is not None and not (isinstance(val, QVariant) and val.isNull()):
            val_str = str(val).strip()
            if val_str.endswith(".0"):
                val_str = val_str[:-2]
            digits = "".join([c for c in val_str if c.isdigit()])
            if len(digits) >= 8:
                return digits[:8]
            elif len(digits) > 0:
                return digits.zfill(8)
            if val_str:
                return val_str[:8]

    # 2. Fallback: Attribute from EA layer
    if dc_geo_idx != -1:
        val = ea_feat.attribute(dc_geo_idx)
        if val is not None and not (isinstance(val, QVariant) and val.isNull()):
            val_str = str(val).strip()
            if val_str.endswith(".0"):
                val_str = val_str[:-2]
            if val_str:
                if len(val_str) > 5 and len(val_str) in (9, 10, 11, 12):
                    return val_str[:5]
                return val_str
    return "Unknown"
