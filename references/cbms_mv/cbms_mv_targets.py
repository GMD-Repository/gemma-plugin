"""
Target Field Resolution for 2027 CBMS Form 2 Map Validation.

Resolves target fields defined directly in algorithm scripts (via TARGET_FIELDS)
against actual layer attribute columns for UI highlighting, focus chips,
auto-scrolling, and Review Dock guidance.
"""
from typing import Dict, List, Optional
import re

# Optional dictionary for legacy / external overrides if needed
CBMS_MV_RULE_TARGET_FIELDS: Dict[str, List[str]] = {}

# Canonical category metadata for 2027 CBMS Form 2 Map Validation checks
CBMS_MV_CATEGORIES: Dict[str, Dict[str, str]] = {
    "missing": {
        "label": "Missing / Blank",
        "desc": "NA or blank values that require field or questionnaire verification",
        "icon": "mActionSelectUnset.svg",
    },
    "invalid": {
        "label": "Invalid Values",
        "desc": "Values not in allowable domain set or outside numeric bounds",
        "icon": "mIconCritical.svg",
    },
    "duplicate": {
        "label": "Duplicate Records",
        "desc": "Duplicate records, building coordinates, or unique identifiers",
        "icon": "mActionEditCopy.svg",
    },
    "for_recoding": {
        "label": "For Recoding",
        "desc": "Text responses in 'others, specify' matching recodable category codes",
        "icon": "mActionCalculateField.svg",
    },
    "for_checking": {
        "label": "For Checking",
        "desc": "Borderline cases for potential recoding or manual confirmation",
        "icon": "mActionFilter.svg",
    },
    "unexpected": {
        "label": "Unexpected / Skipping",
        "desc": "Routing logic skips and Priority D inconsistencies",
        "icon": "mIconQuestion.svg",
    },
    "outlier": {
        "label": "Outliers",
        "desc": "Statistically extreme or unusual figures",
        "icon": "mActionHighlightFeature.svg",
    },
    "mismatch": {
        "label": "Mismatches",
        "desc": "Inconsistent cross-references between datasets or geometry layers",
        "icon": "mActionOptions.svg",
    },
    "other": {
        "label": "Other Checks",
        "desc": "General validation and integrity checks",
        "icon": "mActionOptions.svg",
    },
}


def get_rule_category(val_id: str) -> str:
    """
    Extract the error category key from a validation rule ID.
    Follows the suffix convention: mv_...__<check_type> (e.g., '__missing' -> 'missing').
    """
    if "__" in val_id:
        suffix = val_id.split("__")[-1].strip().lower()
        if suffix in CBMS_MV_CATEGORIES:
            return suffix
        return suffix
    return "other"


def get_category_info(category_key: str) -> Dict[str, str]:
    """Return dictionary with label, desc, and native QGIS icon for a category key."""
    clean_k = str(category_key).strip().lower()
    if clean_k in CBMS_MV_CATEGORIES:
        return CBMS_MV_CATEGORIES[clean_k]
    return {
        "label": clean_k.replace("_", " ").title(),
        "desc": f"Validation checks for {clean_k.replace('_', ' ')}",
        "icon": "mActionOptions.svg",
    }


def resolve_target_columns(
    val_id: str,
    available_fields: List[str],
    custom_target_fields: Optional[List[str]] = None,
) -> List[str]:
    """
    Resolve matching column names from available_fields for a given val_id.
    Matches exact names, stripped sf_/df_/ref_ prefixes, or regex patterns.
    Preserves available_fields order.
    """
    targets = custom_target_fields or CBMS_MV_RULE_TARGET_FIELDS.get(val_id)
    if not targets:
        # Fallback: extract target field from rule ID: mv_2027_hp_<section>_<field>__<type>
        match = re.search(r"mv_\d+_[a-z0-9]+_[a-z0-9]+_(?P<field>.+?)__[a-z0-9]+", val_id)
        if match:
            extracted = match.group("field")
            targets = [extracted]
        else:
            return []

    # Build normalized set of target tokens (both with and without prefixes)
    normalized_targets = set()
    for t in targets:
        t_clean = t.strip().lower()
        normalized_targets.add(t_clean)
        for prefix in ("sf_", "df_", "ref_", "dup_sf_", "dup_"):
            if t_clean.startswith(prefix):
                normalized_targets.add(t_clean[len(prefix):])

    matched = []
    for f in available_fields:
        f_lower = f.lower()
        if f_lower in normalized_targets:
            matched.append(f)
            continue
        for prefix in ("sf_", "df_", "ref_", "dup_sf_", "dup_"):
            if f_lower.startswith(prefix) and f_lower[len(prefix):] in normalized_targets:
                matched.append(f)
                break

    return matched
