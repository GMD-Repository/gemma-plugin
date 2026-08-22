# -*- coding: utf-8 -*-
"""
Phase 7: Final Compliance Sweep.
Global pass enforcing household threshold bounds on all EAs.
"""

from typing import Dict, Any, List
from qgis.core import QgsProcessingException

from ..helpers.constants import _PHASE_LABELS
from ..helpers.classification import is_delineation_candidate, is_merge_candidate
from .phase5_delineate import force_geometric_split


def run_phase_7(
    alg: Any,
    parameters: Dict[str, Any],
    context: Any,
    feedback: Any,
    multi_feedback: Any,
    p1: Dict[str, Any],
    p2: Dict[str, Any],
    p6: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Executes Phase 7: Final Compliance Sweep.
    """
    eas = list(p6["merged_eas"])
    min_household = p1["min_household"]
    max_household = p1["max_household"]
    delineation_candidate_ids = p2.get("delineation_candidate_ids", set())
    merge_candidate_ids = p2.get("merge_candidate_ids", set())
    eadel_indi_col_idx = p1.get("eadel_indi_col_idx", -1)
    full_ea_by_id = p2.get("full_ea_by_id", {})

    multi_feedback.setCurrentStep(6)
    multi_feedback.setProgressText(f"{_PHASE_LABELS[6]}...")
    feedback.pushInfo("Running compliance sweep...")

    compliance_changed = False
    compliance_pass = 0
    max_compliance_passes = 10
    feedback.pushInfo("TEMPORARY BYPASS: Skipping Phase 8 Final Compliance Sweep as requested.")

    while compliance_changed and compliance_pass < max_compliance_passes:
        if multi_feedback.isCanceled():
            raise QgsProcessingException("Algorithm cancelled by user.")
        compliance_changed = False
        compliance_pass += 1

        _pct = int(compliance_pass / max_compliance_passes * 100)
        multi_feedback.setProgress(_pct)
        multi_feedback.setProgressText(
            f"{_PHASE_LABELS[6]} [pass {compliance_pass}/{max_compliance_passes}]..."
        )

        over_idx = [i for i, ea in enumerate(eas) if is_delineation_candidate(ea, max_household, eadel_indi_col_idx, full_ea_by_id, delineation_candidate_ids)]
        under_idx = [i for i, ea in enumerate(eas) if is_merge_candidate(ea, min_household, merge_candidate_ids)]

        if not over_idx and not under_idx:
            break

        feedback.pushInfo(
            f"  Compliance pass {compliance_pass}: "
            f"{len(over_idx)} over-threshold, {len(under_idx)} under-threshold."
        )

        removed = set()
        added = []

        # Fix over-threshold EAs via forced geometric split (only for genuine delineation candidates)
        for i in over_idx:
            if i in removed:
                continue
            ea = eas[i]
            if ea.get("original_id") not in delineation_candidate_ids:
                continue
            if ea.get("from_merge", False):
                continue
            parts = force_geometric_split(ea, max_household, feedback)
            if len(parts) > 1:
                removed.add(i)
                added.extend(parts)
                compliance_changed = True
                feedback.pushWarning(
                    f"[Final Sweep] Over-threshold EA (code={ea['original_code']}, "
                    f"pop={ea['hh_count']}) force-split into {len(parts)} part(s)."
                )
            else:
                feedback.pushWarning(
                    f"[Final Sweep] EA (code={ea['original_code']}, pop={ea['hh_count']}) "
                    f"cannot be split further — truly unresolvable."
                )

        # Fix under-threshold EAs via forced merge with best barangay neighbour
        for i in under_idx:
            if i in removed:
                continue
            ea = eas[i]
            bar = ea["parent_barangay"]

            best_j = -1
            best_score = float("inf")
            for j, nb in enumerate(eas):
                if j == i or j in removed:
                    continue
                if nb["parent_barangay"] != bar:
                    continue
                if is_delineation_candidate(nb):
                    continue
                if nb.get("is_special_ea", False) and not is_merge_candidate(nb):
                    continue
                if ea["geom"].touches(nb["geom"]) or ea["geom"].intersects(nb["geom"]):
                    combined = ea["hh_count"] + nb["hh_count"]
                    if min_household < combined < max_household:
                        score = abs(combined - (max_household - 1))
                        if score < best_score:
                            best_score = score
                            best_j = j

            if best_j == -1:
                for j, nb in enumerate(eas):
                    if j == i or j in removed:
                        continue
                    if nb["parent_barangay"] != bar:
                        continue
                    if is_delineation_candidate(nb):
                        continue
                    if nb.get("is_special_ea", False) and not is_merge_candidate(nb):
                        continue
                    if ea["geom"].touches(nb["geom"]) or ea["geom"].intersects(nb["geom"]):
                        combined = ea["hh_count"] + nb["hh_count"]
                        if combined < max_household:
                            score = abs(combined - (max_household - 1))
                            if score < best_score:
                                best_score = score
                                best_j = j

            if best_j == -1:
                up_centroid = ea["geom"].centroid().asPoint()
                best_dist = float("inf")
                for j, nb in enumerate(eas):
                    if j == i or j in removed:
                        continue
                    if nb["parent_barangay"] != bar:
                        continue
                    if is_delineation_candidate(nb):
                        continue
                    if nb.get("is_special_ea", False) and not is_merge_candidate(nb):
                        continue
                    combined = ea["hh_count"] + nb["hh_count"]
                    if combined < max_household:
                        dist = up_centroid.distance(nb["geom"].centroid().asPoint())
                        if dist < best_dist:
                            best_dist = dist
                            best_j = j

            if best_j != -1:
                nb = eas[best_j]
                dominant = nb if nb["hh_count"] >= ea["hh_count"] else ea
                merged_ea = {
                    "geom": ea["geom"].combine(nb["geom"]).buffer(0.0, 3),
                    "buildings": ea.get("buildings", []) + nb.get("buildings", []),
                    "hh_count": ea["hh_count"] + nb["hh_count"],
                    "original_hhcount": dominant.get("original_hhcount", 0),
                    "original_bldgcount": dominant.get("original_bldgcount", 0),
                    "bldg_count": ea.get("bldg_count", 0) + nb.get("bldg_count", 0),
                    "attributes": list(dominant["attributes"]),
                    "original_id": dominant["original_id"],
                    "original_code": dominant["original_code"],
                    "is_new": True,
                    "from_split": False,
                    "split_by": ea.get("split_by", "none"),
                    "from_merge": True,
                    "parent_barangay": bar,
                }
                removed.add(i)
                removed.add(best_j)
                added.append(merged_ea)
                compliance_changed = True
                merged_hh = merged_ea["hh_count"]
                if merged_hh <= min_household or merged_hh > max_household:
                    feedback.pushWarning(
                        f"[Final Sweep] Merge result out of range: combined={merged_hh} HH "
                        f"(EA {ea['original_code']} + {nb['original_code']}). "
                        f"Expected strictly > {min_household} and <= {max_household}."
                    )
                else:
                    feedback.pushInfo(
                        f"[Final Sweep] Under-threshold EA (code={ea['original_code']}, "
                        f"pop={ea['hh_count']}) merged with (code={nb['original_code']}, "
                        f"pop={nb['hh_count']}) → combined={merged_hh}."
                    )
            else:
                feedback.pushWarning(
                    f"[Final Sweep] EA (code={ea['original_code']}, pop={ea['hh_count']}) "
                    f"has no merge partner in barangay {bar} — truly isolated."
                )

        if removed or added:
            eas = [ea for i, ea in enumerate(eas) if i not in removed] + added

    remaining_violations = [
        ea for ea in eas if ea["hh_count"] < min_household or ea["hh_count"] > max_household
    ]
    if remaining_violations:
        feedback.pushWarning(
            f"Final compliance sweep complete ({compliance_pass} pass(es)): "
            f"{len(remaining_violations)} EA(s) still violate thresholds and could not be resolved."
        )
    else:
        feedback.pushInfo(
            f"Final compliance sweep complete ({compliance_pass} pass(es)): all EAs are within threshold."
        )

    multi_feedback.setProgress(100)

    if multi_feedback.isCanceled():
        raise QgsProcessingException("Algorithm cancelled by user.")

    return {"eas": eas}
