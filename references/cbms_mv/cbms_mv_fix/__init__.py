# -*- coding: utf-8 -*-
"""
2027 CBMS Map Validation Fix Module.
Direct action processes for all CBMS map validations.
"""
from typing import Any, Callable, Optional

from .concatenate_ea_geocode_fix import concatenate_ea_geocode, run_fix as _run_ea_fix
from .delete_selected_features_fix import delete_selected_features, run_fix as _run_del_fix
from .generate_point_geometry_fix import generate_point_geometry, run_fix as _run_geom_fix
from .deduplicate_features_fix import deduplicate_features, run_fix as _run_dup_fix
from .concatenate_bsn_geoid_fix import concatenate_bsn_geoid, run_fix as _run_bsn_fix
from .copy_geometry_to_coordinates_fix import copy_geometry_to_coordinates, run_fix as _run_copy_fix
from .update_datafile_coordinates_fix import update_datafile_coordinates, run_fix as _run_update_coord_fix
from .update_point_geometry_fix import update_point_geometry, run_fix as _run_update_geom_fix
from .common import is_valid_qobject, make_unique_feature_key

_DIRECT_FIX_MAP = {
    "concatenate_ea_geocode": _run_ea_fix,
    "mv_2027_hp_4b_ea_geocode__missing": _run_ea_fix,
    "mv_2027_hp_4b_ea_geocode_missing": _run_ea_fix,
    "generate_point_geometry": _run_geom_fix,
    "generate_point": _run_geom_fix,
    "point_geometry": _run_geom_fix,
    "create_point_geometry": _run_geom_fix,
    "mv_2027_hp_1a_map_uuid__missing": _run_geom_fix,
    "mv_2027_hp_1a_map_uuid_missing": _run_geom_fix,
    "deduplicate_features": _run_dup_fix,
    "mv_2027_hp_4a_longitude__duplicate": _run_dup_fix,
    "mv_2027_hp_4a_longitude_duplicate": _run_dup_fix,
    "concatenate_bsn_geoid": _run_bsn_fix,
    "mv_2027_hp_4b_bsn_geoid__invalid": _run_bsn_fix,
    "mv_2027_hp_4b_bsn_geoid_invalid": _run_bsn_fix,
    "mv_2027_hp_4b_bsn_geoid__missing": _run_bsn_fix,
    "mv_2027_hp_4b_bsn_geoid_missing": _run_bsn_fix,
    "copy_geometry_to_coordinates": _run_copy_fix,
    "copy_geometry": _run_copy_fix,
    "delete_selected_features": _run_del_fix,
    "update_datafiles_coordinates": _run_update_coord_fix,
    "update_datafile_coordinates": _run_update_coord_fix,
    "update_coordinates": _run_update_coord_fix,
    "mv_2027_hp_4a_pos_longit__invalid": _run_update_coord_fix,
    "mv_2027_hp_4a_pos_longit_invalid": _run_update_coord_fix,
    "mv_2027_hp_4a_pos_latitu__invalid": _run_update_coord_fix,
    "mv_2027_hp_4a_pos_latitu_invalid": _run_update_coord_fix,
    "update_point_geometry": _run_update_geom_fix,
    "update_point_geometry_using_sf_longitude_and_sf_latitude": _run_update_geom_fix,
    "update_coordinates_using_sf_longitude_and_sf_latitude": _run_update_geom_fix,
    "update_geometry_using_sf_longitude_and_sf_latitude": _run_update_geom_fix,
}


def get_fix_handler(val_id: str) -> Optional[Callable]:
    """Return the direct executable fix handler callable."""
    if not val_id:
        return None
    clean = str(val_id).strip().lower()
    if clean in _DIRECT_FIX_MAP:
        return _DIRECT_FIX_MAP[clean]
    if "bsn_geoid" in clean:
        return _run_bsn_fix
    if "ea_geocode" in clean:
        return _run_ea_fix
    if any(k in clean for k in ("update_point_geom", "update_geometry", "sf_longitude", "sf_latitude")):
        return _run_update_geom_fix
    if any(k in clean for k in ("update_datafile", "datafile_coord", "datafile_coordinate", "update_coord", "pos_longit", "pos_latitu")):
        return _run_update_coord_fix
    if any(k in clean for k in ("copy_geometry", "copy_geom", "geometry_to_coord")):
        return _run_copy_fix
    if any(k in clean for k in ("delete_selected", "soft_delete")):
        return _run_del_fix
    if any(k in clean for k in ("deduplicate", "duplicate")):
        return _run_dup_fix
    if any(k in clean for k in ("generate_point", "point_geometry", "create_point", "map_uuid")):
        return _run_geom_fix
    return _run_ea_fix


def has_fix(val_id: str) -> bool:
    """Check if a fix handler exists."""
    return get_fix_handler(val_id) is not None


__all__ = [
    "concatenate_ea_geocode",
    "delete_selected_features",
    "generate_point_geometry",
    "deduplicate_features",
    "concatenate_bsn_geoid",
    "copy_geometry_to_coordinates",
    "update_datafile_coordinates",
    "update_point_geometry",
    "get_fix_handler",
    "has_fix",
    "is_valid_qobject",
    "make_unique_feature_key",
]
