# -*- coding: utf-8 -*-
"""
2027 CBMS Map Validation Automated Fix Module Registry.

Discovers and loads fix algorithms matching the naming convention:
    {val_id}_fix.py
"""
import importlib
import importlib.util
import os
from typing import Any, Callable, Optional


def has_fix(val_id: str) -> bool:
    """Check if an automated fix algorithm file exists for the given validation ID."""
    if not val_id:
        return False
    clean_id = str(val_id).strip()
    file_name = f"{clean_id}_fix.py"
    current_dir = os.path.dirname(__file__)
    return os.path.isfile(os.path.join(current_dir, file_name))


def get_fix_handler(val_id: str) -> Optional[Callable]:
    """
    Dynamically locate and return the run_fix callable for a validation ID.
    Looks for references/cbms_mv/cbms_mv_fix/{val_id}_fix.py
    """
    if not has_fix(val_id):
        return None

    clean_id = str(val_id).strip()
    module_name = f"{clean_id}_fix"

    try:
        mod = importlib.import_module(f".{module_name}", package=__name__)
        if hasattr(mod, "run_fix"):
            return getattr(mod, "run_fix")
    except Exception:
        pass

    try:
        file_path = os.path.join(os.path.dirname(__file__), f"{module_name}.py")
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "run_fix"):
                return getattr(mod, "run_fix")
    except Exception:
        pass

    return None
