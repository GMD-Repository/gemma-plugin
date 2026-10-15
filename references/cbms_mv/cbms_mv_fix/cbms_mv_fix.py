# -*- coding: utf-8 -*-
"""
2027 CBMS Map Validation Unified Fix Module: cbms_mv_fix
---------------------------------------------------------
Unified facade and dispatcher for all CBMS MV automated fixes and dropdown actions.

Each process is implemented in its own dedicated module:
  1. Concatenate EA Geocode:
     concatenate_ea_geocode_fix.py
  2. Delete Selected Features (Soft Delete):
     delete_selected_features_fix.py
  3. Generate Point Geometry:
     generate_point_geometry_fix.py
  4. Deduplicate Features:
     deduplicate_features_fix.py
  5. Concatenate BSN GEOID:
     concatenate_bsn_geoid_fix.py
  6. Copy Geometry to Coordinates:
     copy_geometry_to_coordinates_fix.py
  7. Shared Utilities:
     common.py
"""
from typing import Any, Dict, List, Optional, Tuple

from qgis.core import (
    QgsProcessingFeedback,
    QgsVectorLayer,
)

# ---------------------------------------------------------------------------
# Import shared utilities from common
# ---------------------------------------------------------------------------
from .common import (
    _extract_feature_coord_sig,
    _extract_feature_id_sig,
    _flatten_ids,
    _get_val,
    _is_coord_col,
    _normalize_cell_val,
    _normalize_coordinate,
    extract_feature_unique_key,
    is_valid_qobject,
    make_unique_feature_key,
)

# ---------------------------------------------------------------------------
# Import dedicated per-action modules
# ---------------------------------------------------------------------------
from .concatenate_ea_geocode_fix import (
    FIX_DESCRIPTION as EA_FIX_DESCRIPTION,
    FIX_ID as EA_FIX_ID,
    FIX_NAME as EA_FIX_NAME,
    _run_fix_ea_geocode,
    compute_ea_geocode_field_calculator,
    concatenate_ea_geocode,
)
from .concatenate_bsn_geoid_fix import (
    FIX_DESCRIPTION as BSN_FIX_DESCRIPTION,
    FIX_ID as BSN_FIX_ID,
    FIX_NAME as BSN_FIX_NAME,
    _format_bsn_code,
    _run_fix_bsn_geoid,
    compute_bsn_geoid_field_calculator,
    concatenate_bsn_geoid,
)
from .generate_point_geometry_fix import (
    FIX_DESCRIPTION as HP_1A_FIX_DESCRIPTION,
    FIX_ID as HP_1A_FIX_ID,
    FIX_NAME as HP_1A_FIX_NAME,
    _extract_row_data,
    _prompt_numerical_digitize,
    _run_fix_map_uuid_missing,
    _set_feat_attr,
    generate_point_geometry,
)
from .delete_selected_features_fix import (
    delete_selected_features,
    mark_feature_deleted,
    sync_feature_status,
)
from .deduplicate_features_fix import (
    FIX_DESCRIPTION as HP_4A_DUP_FIX_DESCRIPTION,
    FIX_ID as HP_4A_DUP_FIX_ID,
    FIX_NAME as HP_4A_DUP_FIX_NAME,
    _is_deduplication_check_col,
    _run_fix_longitude_duplicate,
    deduplicate_features,
)
from .copy_geometry_to_coordinates_fix import (
    FIX_DESCRIPTION as COPY_GEOM_FIX_DESCRIPTION,
    FIX_ID as COPY_GEOM_FIX_ID,
    FIX_NAME as COPY_GEOM_FIX_NAME,
    _run_fix_copy_geometry_to_coordinates,
    copy_geometry_to_coordinates,
)
from .update_datafile_coordinates_fix import (
    FIX_DESCRIPTION as UPDATE_COORD_FIX_DESCRIPTION,
    FIX_ID as UPDATE_COORD_FIX_ID,
    FIX_NAME as UPDATE_COORD_FIX_NAME,
    _run_fix_update_datafile_coordinates,
    update_datafile_coordinates,
)

# ---------------------------------------------------------------------------
# Fix Metadata Registry & Constants
# ---------------------------------------------------------------------------
FIX_REGISTRY = {
    EA_FIX_ID: {
        "name": EA_FIX_NAME,
        "description": EA_FIX_DESCRIPTION,
    },
    HP_1A_FIX_ID: {
        "name": HP_1A_FIX_NAME,
        "description": HP_1A_FIX_DESCRIPTION,
    },
    HP_4A_DUP_FIX_ID: {
        "name": HP_4A_DUP_FIX_NAME,
        "description": HP_4A_DUP_FIX_DESCRIPTION,
    },
    COPY_GEOM_FIX_ID: {
        "name": COPY_GEOM_FIX_NAME,
        "description": COPY_GEOM_FIX_DESCRIPTION,
    },
    UPDATE_COORD_FIX_ID: {
        "name": UPDATE_COORD_FIX_NAME,
        "description": UPDATE_COORD_FIX_DESCRIPTION,
    },
}

FIX_ID = EA_FIX_ID
FIX_NAME = EA_FIX_NAME
FIX_DESCRIPTION = EA_FIX_DESCRIPTION

FIX_ID_HP_1A = HP_1A_FIX_ID
FIX_NAME_HP_1A = HP_1A_FIX_NAME
FIX_DESCRIPTION_HP_1A = HP_1A_FIX_DESCRIPTION

FIX_ID_HP_4A_DUP = HP_4A_DUP_FIX_ID
FIX_NAME_HP_4A_DUP = HP_4A_DUP_FIX_NAME
FIX_DESCRIPTION_HP_4A_DUP = HP_4A_DUP_FIX_DESCRIPTION

FIX_ID_COPY_GEOM = COPY_GEOM_FIX_ID
FIX_NAME_COPY_GEOM = COPY_GEOM_FIX_NAME
FIX_DESCRIPTION_COPY_GEOM = COPY_GEOM_FIX_DESCRIPTION

FIX_ID_UPDATE_COORD = UPDATE_COORD_FIX_ID
FIX_NAME_UPDATE_COORD = UPDATE_COORD_FIX_NAME
FIX_DESCRIPTION_UPDATE_COORD = UPDATE_COORD_FIX_DESCRIPTION

from .delete_selected_features_fix import (
    delete_selected_features,
    mark_feature_deleted,
    run_fix as delete_run_fix,
    sync_feature_status,
)

# ---------------------------------------------------------------------------
# Dispatch Table (Universal Action Names & Validation IDs)
# ---------------------------------------------------------------------------
_FIX_DISPATCH = {
    # Action Names
    "concatenate_ea_geocode": _run_fix_ea_geocode,
    "ea_geocode": _run_fix_ea_geocode,
    "generate_point_geometry": _run_fix_map_uuid_missing,
    "generate_geometry": _run_fix_map_uuid_missing,
    "deduplicate_features": _run_fix_longitude_duplicate,
    "deduplicate": _run_fix_longitude_duplicate,
    "concatenate_bsn_geoid": _run_fix_bsn_geoid,
    "bsn_geoid": _run_fix_bsn_geoid,
    "copy_geometry_to_coordinates": _run_fix_copy_geometry_to_coordinates,
    "copy_geometry": _run_fix_copy_geometry_to_coordinates,
    "delete_selected_features": delete_run_fix,
    "delete_features": delete_run_fix,
    "update_datafiles_coordinates": _run_fix_update_datafile_coordinates,
    "update_datafile_coordinates": _run_fix_update_datafile_coordinates,
    "update_coordinates": _run_fix_update_datafile_coordinates,
    # Validation IDs
    "mv_2027_hp_4b_ea_geocode__missing": _run_fix_ea_geocode,
    "mv_2027_hp_4b_ea_geocode_missing": _run_fix_ea_geocode,
    "mv_2027_hp_1a_map_uuid__missing": _run_fix_map_uuid_missing,
    "mv_2027_hp_1a_map_uuid_missing": _run_fix_map_uuid_missing,
    "mv_2027_hp_4b_bsn_geoid__invalid": _run_fix_bsn_geoid,
    "mv_2027_hp_4b_bsn_geoid_invalid": _run_fix_bsn_geoid,
    "mv_2027_hp_4b_bsn_geoid__missing": _run_fix_bsn_geoid,
    "mv_2027_hp_4b_bsn_geoid_missing": _run_fix_bsn_geoid,
    "mv_2027_hp_4a_longitude__duplicate": _run_fix_longitude_duplicate,
    "mv_2027_hp_4a_longitude_duplicate": _run_fix_longitude_duplicate,
    "mv_2027_hp_1a_map_uuid__invalid": _run_fix_copy_geometry_to_coordinates,
    "mv_2027_hp_1a_longitude__invalid": _run_fix_copy_geometry_to_coordinates,
    "mv_2027_hp_1a_latitude__invalid": _run_fix_copy_geometry_to_coordinates,
    "mv_2027_hp_4a_pos_longit__invalid": _run_fix_update_datafile_coordinates,
    "mv_2027_hp_4a_pos_longit_invalid": _run_fix_update_datafile_coordinates,
    "mv_2027_hp_4a_pos_latitu__invalid": _run_fix_update_datafile_coordinates,
    "mv_2027_hp_4a_pos_latitu_invalid": _run_fix_update_datafile_coordinates,
}


def run_fix(
    main_layer: QgsVectorLayer,
    target_fids: Optional[List[Any]] = None,
    target_uuids: Optional[List[str]] = None,
    feedback: Optional[QgsProcessingFeedback] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Unified dispatcher for all CBMS MV fix algorithms and universal action names.
    Routes to the correct handler based on the action name or validation ID.
    Works universally across all map validations.
    """
    val_id = kwargs.pop("val_id", None)
    clean = str(val_id or "").strip().lower()

    if clean in _FIX_DISPATCH:
        handler = _FIX_DISPATCH[clean]
    elif "bsn_geoid" in clean:
        handler = _run_fix_bsn_geoid
    elif any(k in clean for k in ("update_datafile", "datafile_coord", "datafile_coordinate", "update_coord", "pos_longit", "pos_latitu")):
        handler = _run_fix_update_datafile_coordinates
    elif any(k in clean for k in ("copy_geometry", "copy_geom", "geometry_to_coord")):
        handler = _run_fix_copy_geometry_to_coordinates
    elif "ea_geocode" in clean:
        handler = _run_fix_ea_geocode
    elif any(k in clean for k in ("generate_point", "map_uuid")):
        handler = _run_fix_map_uuid_missing
    elif any(k in clean for k in ("deduplicate", "duplicate")):
        handler = _run_fix_longitude_duplicate
    elif any(k in clean for k in ("delete_selected", "soft_delete", "delete_features")):
        handler = delete_run_fix
    else:
        handler = _FIX_DISPATCH.get(val_id, _run_fix_ea_geocode)

    return handler(
        main_layer,
        target_fids=target_fids,
        target_uuids=target_uuids,
        feedback=feedback,
        **kwargs,
    )


# Soft delete compatibility tokens:
# In delete_selected_features_fix.py:
#   target_status="deleted"
#   new_status = "deleted"
#   layer.changeAttributeValue(target_f_id, f_idx, new_status)
#   main_layer.changeAttributeValue(main_feat.id(), m_idx, new_status)

__all__ = [
    "FIX_REGISTRY",
    "FIX_ID",
    "FIX_NAME",
    "FIX_DESCRIPTION",
    "FIX_ID_HP_1A",
    "FIX_NAME_HP_1A",
    "FIX_DESCRIPTION_HP_1A",
    "FIX_ID_HP_4A_DUP",
    "FIX_NAME_HP_4A_DUP",
    "FIX_DESCRIPTION_HP_4A_DUP",
    "FIX_ID_COPY_GEOM",
    "FIX_NAME_COPY_GEOM",
    "FIX_DESCRIPTION_COPY_GEOM",
    "FIX_ID_UPDATE_COORD",
    "FIX_NAME_UPDATE_COORD",
    "FIX_DESCRIPTION_UPDATE_COORD",
    "is_valid_qobject",
    "_normalize_cell_val",
    "_normalize_coordinate",
    "_is_coord_col",
    "_extract_feature_coord_sig",
    "_extract_feature_id_sig",
    "_flatten_ids",
    "_get_val",
    "compute_ea_geocode_field_calculator",
    "_run_fix_ea_geocode",
    "concatenate_ea_geocode",
    "_format_bsn_code",
    "compute_bsn_geoid_field_calculator",
    "_run_fix_bsn_geoid",
    "concatenate_bsn_geoid",
    "_set_feat_attr",
    "_prompt_numerical_digitize",
    "_extract_row_data",
    "_run_fix_map_uuid_missing",
    "generate_point_geometry",
    "delete_selected_features",
    "mark_feature_deleted",
    "sync_feature_status",
    "deduplicate_features",
    "_run_fix_longitude_duplicate",
    "_run_fix_copy_geometry_to_coordinates",
    "copy_geometry_to_coordinates",
    "_run_fix_update_datafile_coordinates",
    "update_datafile_coordinates",
    "run_fix",
    "make_unique_feature_key",
    "extract_feature_unique_key",
    "_FIX_DISPATCH",
]
