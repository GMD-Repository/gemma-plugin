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

    # Handle underscore variations: single _ vs double __
    if "__" in clean_id:
        candidates.append(f"{clean_id.replace('__', '_')}_fix")
    else:
        for suffix in ("missing", "invalid", "duplicate"):
            if f"_{suffix}" in clean_id and f"__{suffix}" not in clean_id:
                candidates.append(f"{clean_id.replace(f'_{suffix}', f'__{suffix}')}_fix")

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
    """
    if not val_id:
        return None

    file_path = _find_fix_file_path(val_id)
    if not file_path:
        return None

    stem = os.path.splitext(os.path.basename(file_path))[0]

    # Try relative package import first if within cbms_mv_fix directory
    current_dir = os.path.dirname(__file__)
    if os.path.dirname(file_path) == current_dir:
        try:
            mod = importlib.import_module(f".{stem}", package=__name__)
            mod = importlib.reload(mod)
            if hasattr(mod, "run_fix"):
                return getattr(mod, "run_fix")
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
    try:
        spec = importlib.util.spec_from_file_location(stem, file_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            import sys
            sys.modules[stem] = mod
            spec.loader.exec_module(mod)
            if hasattr(mod, "run_fix"):
                return getattr(mod, "run_fix")
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

    return None
