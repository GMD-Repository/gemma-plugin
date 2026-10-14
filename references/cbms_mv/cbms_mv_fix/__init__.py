# -*- coding: utf-8 -*-
"""
2027 CBMS Map Validation Automated Fix Module Registry.

Discovers and loads fix algorithms matching the naming convention:
    {val_id}_fix.py
from references/cbms_mv/cbms_mv_fix/ (and parent references/cbms_mv/ fallback).
"""
import importlib
import importlib.util
import os
from typing import Any, Callable, List, Optional


def _get_candidate_file_stems(val_id: str) -> List[str]:
    """Generate candidate file stems for finding fix algorithms, handling underscore variations."""
    if not val_id:
        return []
    clean_id = str(val_id).strip()
    candidates = [f"{clean_id}_fix"]

    # Map validation IDs / action names to their dedicated process module file stems
    _ACTION_STEM_MAP = {
        "mv_2027_hp_4b_ea_geocode__missing": "concatenate_ea_geocode_fix",
        "mv_2027_hp_4b_ea_geocode_missing": "concatenate_ea_geocode_fix",
        "mv_2027_hp_1a_map_uuid__missing": "generate_point_geometry_fix",
        "mv_2027_hp_1a_map_uuid_missing": "generate_point_geometry_fix",
        "mv_2027_hp_4a_longitude__duplicate": "deduplicate_features_fix",
        "mv_2027_hp_4a_longitude_duplicate": "deduplicate_features_fix",
        "mv_2027_hp_4b_bsn_geoid__invalid": "concatenate_bsn_geoid_fix",
        "mv_2027_hp_4b_bsn_geoid_invalid": "concatenate_bsn_geoid_fix",
        "mv_2027_hp_4b_bsn_geoid__missing": "concatenate_bsn_geoid_fix",
        "mv_2027_hp_4b_bsn_geoid_missing": "concatenate_bsn_geoid_fix",
        "copy_geometry_to_coordinates": "copy_geometry_to_coordinates_fix",
        "copy_geometry": "copy_geometry_to_coordinates_fix",
        "delete_selected_features": "delete_selected_features_fix",
    }
    if clean_id in _ACTION_STEM_MAP:
        candidates.append(_ACTION_STEM_MAP[clean_id])
    if "bsn_geoid" in clean_id.lower():
        candidates.append("concatenate_bsn_geoid_fix")
    if any(k in clean_id.lower() for k in ("copy_geometry", "geometry_to_coord")):
        candidates.append("copy_geometry_to_coordinates_fix")

    # Handle underscore variations: single _ vs double __
    if "__" in clean_id:
        candidates.append(f"{clean_id.replace('__', '_')}_fix")
    else:
        for suffix in ("missing", "invalid", "duplicate"):
            if f"_{suffix}" in clean_id and f"__{suffix}" not in clean_id:
                candidates.append(f"{clean_id.replace(f'_{suffix}', f'__{suffix}')}_fix")

    # Fallback to unified cbms_mv_fix facade
    candidates.append("cbms_mv_fix")

    # Preserve order while removing duplicates
    seen = set()
    result = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


def _find_fix_file_path(val_id: str) -> Optional[str]:
    """Search for the fix python file in cbms_mv_fix/ and parent cbms_mv/ directory."""
    if not val_id:
        return None
    current_dir = os.path.dirname(__file__)
    parent_dir = os.path.dirname(current_dir)
    dirs_to_check = [current_dir, parent_dir]

    for stem in _get_candidate_file_stems(val_id):
        for d in dirs_to_check:
            fp = os.path.join(d, f"{stem}.py")
            if os.path.isfile(fp):
                return fp
    return None


def has_fix(val_id: str) -> bool:
    """Check if an automated fix algorithm file exists for the given validation ID."""
    return _find_fix_file_path(val_id) is not None


def get_fix_handler(val_id: str) -> Optional[Callable]:
    """
    Dynamically locate and return the run_fix callable for a validation ID.
    Looks for references/cbms_mv/cbms_mv_fix/{val_id}_fix.py

    If the resolved module is the unified cbms_mv_fix module, the returned
    callable automatically injects val_id so the dispatcher routes correctly.
    """
    if not val_id:
        return None

    file_path = _find_fix_file_path(val_id)
    if not file_path:
        return None

    stem = os.path.splitext(os.path.basename(file_path))[0]

    mod = None

    # Try relative package import first if within cbms_mv_fix directory
    current_dir = os.path.dirname(__file__)
    if os.path.dirname(file_path) == current_dir:
        try:
            mod = importlib.import_module(f".{stem}", package=__name__)
            mod = importlib.reload(mod)
        except Exception as exc:
            try:
                from qgis.core import Qgis, QgsMessageLog
                QgsMessageLog.logMessage(
                    f"Failed relative import of fix module {stem}: {exc}",
                    "CBMS MV",
                    Qgis.Warning,
                )
            except Exception:
                pass

    # Load directly from spec / file path
    if mod is None or not hasattr(mod, "run_fix"):
        try:
            spec = importlib.util.spec_from_file_location(stem, file_path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                import sys
                sys.modules[stem] = mod
                spec.loader.exec_module(mod)
        except Exception as exc:
            try:
                from qgis.core import Qgis, QgsMessageLog
                QgsMessageLog.logMessage(
                    f"Failed spec loader execution of fix module {stem} ({file_path}): {exc}",
                    "CBMS MV",
                    Qgis.Critical,
                )
            except Exception:
                pass

    if mod is None or not hasattr(mod, "run_fix"):
        return None

    run_fix_fn = getattr(mod, "run_fix")

    # If the module is the unified cbms_mv_fix (has _FIX_DISPATCH), wrap the
    # callable to inject val_id automatically so the dispatcher routes correctly.
    if hasattr(mod, "_FIX_DISPATCH"):
        _captured_val_id = val_id

        def _dispatched_run_fix(main_layer, **kwargs):
            kwargs["val_id"] = _captured_val_id
            return run_fix_fn(main_layer, **kwargs)

        return _dispatched_run_fix

    return run_fix_fn


try:
    from .cbms_mv_fix import (
        copy_geometry_to_coordinates,
        concatenate_ea_geocode,
        concatenate_bsn_geoid,
        generate_point_geometry,
        delete_selected_features,
        deduplicate_features,
        run_fix,
    )
except ImportError:
    pass

