from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsSpatialIndex,
    QgsProcessingException,
    NULL,
)
from qgis.PyQt.QtCore import QVariant

from ..helpers.constants import _PHASE_LABELS, yield_to_ui
from ..helpers.spatial import resolve_ea_parent_barangay


def run_phase_4(alg, parameters, context, feedback, multi_feedback, p1, p2, previous_ea_count):
    """
    Executes Phase 4 (Loading Previous EAs into Memory & Active Barangay Filtering), including:
    - Identifying needed EAs (candidates and contiguous merge partners)
    - Filtering active barangays containing candidates
    - Constructing structured in-memory EA dictionaries with building points and household counts
    - Checking threshold compliance for Special EAs
    - Calculating running EA counts per parent barangay

    Returns state dictionary containing:
    - eas: List[dict] of active EA records
    - active_barangays: Set[str]
    - needed_ea_ids: Set[int]
    - max_ea_number: Dict[str, int]
    """
    all_ea_features = p1["all_ea_features"]
    previous_ea_source = p1["previous_ea_source"]
    household_field = p1["household_field"]
    ea_id_field = p1["ea_id_field"]
    gap_source = p1["gap_source"]
    overlap_source = p1["overlap_source"]
    special_ea_info = p1["special_ea_info"]
    special_ea_ids = p1["special_ea_ids"]
    min_household = p1["min_household"]
    barangay_index = p1["barangay_index"]
    barangay_by_id = p1["barangay_by_id"]
    _dc_geo_idx = p1["_dc_geo_idx"]
    barangay_id_field = p1["barangay_id_field"]

    delineation_candidate_ids = p2["delineation_candidate_ids"]
    merge_candidate_ids = p2["merge_candidate_ids"]
    ea_id_to_buildings = p2["ea_id_to_buildings"]

    def _resolve_bar(feat):
        return resolve_ea_parent_barangay(
            feat, _dc_geo_idx, barangay_id_field, barangay_index, barangay_by_id
        )

    multi_feedback.setCurrentStep(3)
    multi_feedback.setProgressText(f"{_PHASE_LABELS[3]} [0/{previous_ea_count:,}]...")
    feedback.pushInfo("Recalculating household counts...")

    def get_field_val(f: QgsFeature, fname: str, default=0):
        if not f or not f.isValid():
            return default
        flds = f.fields()
        idx = flds.indexOf(fname)
        if idx == -1:
            for j in range(flds.count()):
                if flds.at(j).name().lower() == fname.lower():
                    idx = j
                    break
        if idx != -1:
            val = f.attribute(idx)
            if val is not None and val != NULL and not (isinstance(val, QVariant) and val.isNull()):
                try:
                    return float(val) if isinstance(default, float) else int(round(float(val)))
                except (TypeError, ValueError):
                    return val
        return default

    prev_ea_pop_idx = previous_ea_source.fields().indexOf(household_field)

    # ── Pre-calculate Special EA HH counts (especially OVERLAP Special EAs) ───────────
    special_ea_hh = {}
    for feat in all_ea_features:
        if feat.id() in special_ea_ids:
            bldgs = ea_id_to_buildings.get(feat.id(), [])
            hh_val = get_field_val(feat, "hhcount", 0.0)
            if hh_val > 0.0:
                special_ea_hh[feat.id()] = hh_val
            elif bldgs:
                special_ea_hh[feat.id()] = sum(b['pop'] for b in bldgs)
            else:
                special_ea_hh[feat.id()] = 0.0

    ea_to_overlap_hh = {}
    for spec_id, spec_info in special_ea_info.items():
        if spec_info.get('special_type') == 'OVERLAP':
            spec_hh = special_ea_hh.get(spec_id, 0.0)
            for p_id in spec_info.get('parent_ea_ids', []):
                ea_to_overlap_hh[p_id] = ea_to_overlap_hh.get(p_id, 0.0) + spec_hh

    # Adjust delineation candidates affected by overlaps
    for feat in all_ea_features:
        if feat.id() in special_ea_ids:
            continue
        if feat.id() in ea_to_overlap_hh:
            overlap_hh = ea_to_overlap_hh[feat.id()]
            if overlap_hh > 0:
                orig_hh = get_field_val(feat, "hhcount", 0.0)
                if orig_hh <= 0.0 and feat.id() in ea_id_to_buildings:
                    orig_hh = sum(b['pop'] for b in ea_id_to_buildings[feat.id()])
                effective_hh = max(0.0, orig_hh - overlap_hh)
                _ean = feat.attribute(ea_id_field)
                _ean_str = str(_ean).strip() if _ean is not None else ""

                if feat.id() in delineation_candidate_ids or orig_hh >= max_household:
                    if effective_hh < max_household:
                        if feat.id() in delineation_candidate_ids:
                            delineation_candidate_ids.remove(feat.id())
                        feedback.pushInfo(
                            f"[EA {_ean_str}] Overlap Special EA detected (-{overlap_hh:.0f} HH). "
                            f"Adjusted HH ({effective_hh:.0f}) is below max threshold ({max_household}). "
                            f"Bypassing delineation."
                        )
                        if effective_hh <= min_household:
                            merge_candidate_ids.add(feat.id())
                    else:
                        feedback.pushInfo(
                            f"[EA {_ean_str}] Overlap Special EA detected (-{overlap_hh:.0f} HH). "
                            f"Adjusted HH ({effective_hh:.0f}) still exceeds max threshold ({max_household}). "
                            f"Proceeding with delineation."
                        )

    needed_ea_ids = set()
    active_barangays = set()

    temp_index = QgsSpatialIndex()
    ea_by_id = {}
    for feat in all_ea_features:
        temp_index.insertFeature(feat)
        ea_by_id[feat.id()] = feat

    for feat in all_ea_features:
        _ean = feat.attribute(ea_id_field)
        _ean_str = str(_ean).strip() if _ean is not None else ""

        _orig_hhcount = get_field_val(feat, "hhcount", 0.0)
        if feat.id() in ea_to_overlap_hh and feat.id() not in special_ea_ids:
            _orig_hhcount = max(0.0, _orig_hhcount - ea_to_overlap_hh[feat.id()])

        is_delineation = feat.id() in delineation_candidate_ids
        is_merge = feat.id() in merge_candidate_ids or _orig_hhcount == 0.0

        if is_delineation:
            needed_ea_ids.add(feat.id())
            bar_geo = _resolve_bar(feat)
            if bar_geo:
                active_barangays.add(bar_geo)
        elif is_merge:
            needed_ea_ids.add(feat.id())
            bar_geo = _resolve_bar(feat)
            if bar_geo:
                active_barangays.add(bar_geo)
            geom = feat.geometry()
            if geom and not geom.isEmpty():
                candidates = temp_index.intersects(geom.boundingBox())
                for cid in candidates:
                    if cid == feat.id():
                        continue
                    nb_feat = ea_by_id[cid]
                    if _resolve_bar(nb_feat) == bar_geo:
                        if geom.touches(nb_feat.geometry()) or geom.intersects(nb_feat.geometry()):
                            needed_ea_ids.add(cid)

    feedback.pushInfo(f"Found {len(active_barangays)} active barangay(s) containing candidates.")
    feedback.pushInfo(
        f"Bypassing non-candidate/non-partner EAs. Loading only {len(needed_ea_ids)} EA(s) for processing."
    )

    eas = []
    _ea_load_count = 0
    _ea_load_last_pct = -1
    for feat in all_ea_features:
        if multi_feedback.isCanceled():
            raise QgsProcessingException("Algorithm cancelled by user.")
        _ea_load_count += 1
        yield_to_ui(_ea_load_count, 100)
        if previous_ea_count > 0:
            _ea_pct = int(_ea_load_count / previous_ea_count * 100)
            if _ea_pct != _ea_load_last_pct:
                multi_feedback.setProgress(_ea_pct)
                multi_feedback.setProgressText(
                    f"{_PHASE_LABELS[3]} [{_ea_load_count:,}/{previous_ea_count:,}]..."
                )
                _ea_load_last_pct = _ea_pct

        if feat.id() not in needed_ea_ids:
            continue

        bar_geo = _resolve_bar(feat)
        clean_geom = QgsGeometry(feat.geometry())
        assigned_bldgs = ea_id_to_buildings.get(feat.id(), [])
        _orig_hhcount = get_field_val(feat, "hhcount", 0.0)
        if feat.id() in ea_to_overlap_hh and feat.id() not in special_ea_ids:
            _orig_hhcount = max(0.0, _orig_hhcount - ea_to_overlap_hh[feat.id()])

        _orig_bldgcount = get_field_val(feat, "bldgcount", 0)
        if _orig_bldgcount <= 0 and assigned_bldgs:
            _orig_bldgcount = len(assigned_bldgs)

        _ean = feat.attribute(ea_id_field)
        _ean_str = str(_ean).strip() if _ean is not None else ""
        _bldg_pt_count = len(assigned_bldgs)
        if _orig_hhcount > 0:
            _ea_hh_count = _orig_hhcount
            if assigned_bldgs:
                raw_pop_sum = sum(b['pop'] for b in assigned_bldgs)
                if raw_pop_sum > 0:
                    scale = _orig_hhcount / raw_pop_sum
                    for b in assigned_bldgs:
                        b['pop'] = b['pop'] * scale
                else:
                    per_bldg = _orig_hhcount / len(assigned_bldgs)
                    for b in assigned_bldgs:
                        b['pop'] = per_bldg
        else:
            _ea_hh_count = sum(b['pop'] for b in assigned_bldgs) if assigned_bldgs else 0.0
            _orig_hhcount = _ea_hh_count

        _bldgpoints_value = _ea_hh_count / _bldg_pt_count if _bldg_pt_count > 0 else 0.0
        _total_bldg_val = sum(
            b.get('bldgpoints_value') if b.get('bldgpoints_value') is not None else b['pop']
            for b in assigned_bldgs
        )
        for b in assigned_bldgs:
            val = b.get('bldgpoints_value')
            if val is None:
                val = b['pop']
            b['bldgpoints_value'] = val / _total_bldg_val if _total_bldg_val > 0.0 else 0.0

        ea_dict = {
            'geom': clean_geom,
            'buildings': assigned_bldgs,
            'hh_count': _ea_hh_count,
            'original_hhcount': _orig_hhcount,
            'original_bldgcount': _orig_bldgcount,
            'bldg_count': _bldg_pt_count,
            'bldgpoints_value': _bldgpoints_value,
            'attributes': feat.attributes(),
            'original_id': feat.id(),
            'original_code': _ean_str,
            'is_new': False,
            'split_by': 'none',
            'parent_barangay': bar_geo,
        }

        if (gap_source is not None or overlap_source is not None) and feat.id() in special_ea_ids:
            spec_info = special_ea_info[feat.id()]
            ea_dict['is_special_ea'] = True
            ea_dict['ea_type'] = 'SPECIAL'
            ea_dict['special_type'] = spec_info['special_type']
            ea_dict['source_id'] = spec_info['source_id']
            ea_dict['remarks'] = spec_info['remarks']
            ea_dict['is_new'] = True

            if _ea_hh_count >= min_household:
                if feat.id() in merge_candidate_ids:
                    merge_candidate_ids.remove(feat.id())

        eas.append(ea_dict)

    max_ea_number = {}
    for feat in all_ea_features:
        bar_geo = _resolve_bar(feat)
        if not bar_geo or bar_geo == "Unknown":
            continue
        max_ea_number[bar_geo] = max_ea_number.get(bar_geo, 0) + 1

    for pop_fname in [household_field, "hhcount", "population", "household"]:
        pop_idx = previous_ea_source.fields().indexOf(pop_fname)
        if pop_idx != -1:
            for ea in eas:
                ea['attributes'][pop_idx] = ea['hh_count']
    multi_feedback.setProgress(100)

    if multi_feedback.isCanceled():
        raise QgsProcessingException("Algorithm cancelled by user.")

    return {
        "eas": eas,
        "active_barangays": active_barangays,
        "needed_ea_ids": needed_ea_ids,
        "max_ea_number": max_ea_number,
    }
