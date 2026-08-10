# -*- coding: utf-8 -*-
"""
Phase 8: Output Feature Generation & Writing.
Spatially sorts EAs, cleans unsnapped boundary vertices, writes features to sinks,
and renders HTML execution summary tables.
"""

import math
from typing import Dict, Any, List
from PyQt5.QtCore import QVariant
from qgis.core import (
    QgsFeatureSink,
    QgsProcessingException,
    QgsWkbTypes,
    QgsGeometry,
    QgsSpatialIndex,
    QgsFeature,
    QgsCoordinateTransform,
    QgsFields,
    QgsField,
)

from ..helpers.constants import _PHASE_LABELS, yield_to_ui
from ..helpers.geometry import get_polygons_from_geom


def clean_and_remove_holes(geometry: QgsGeometry, target_crs: Any, remove_holes: bool = True) -> QgsGeometry:
    if geometry.isEmpty():
        return geometry

    flat_type = QgsWkbTypes.flatType(geometry.wkbType())
    sliver_limit = 1e-9 if target_crs.isGeographic() else 1.0

    if flat_type == QgsWkbTypes.Polygon:
        poly_pts = geometry.asPolygon()
        if poly_pts:
            ext_poly = QgsGeometry.fromPolygonXY([poly_pts[0]])
            if ext_poly.area() >= sliver_limit:
                if remove_holes:
                    return ext_poly
                else:
                    return geometry
        return QgsGeometry()
    elif flat_type == QgsWkbTypes.MultiPolygon:
        multipoly_pts = geometry.asMultiPolygon()
        new_multipoly = []
        for poly in multipoly_pts:
            if poly:
                ext_poly = QgsGeometry.fromPolygonXY([poly[0]])
                if ext_poly.area() >= sliver_limit:
                    if remove_holes:
                        new_multipoly.append([poly[0]])
                    else:
                        new_multipoly.append(poly)
        if new_multipoly:
            return QgsGeometry.fromMultiPolygonXY(new_multipoly)
        return QgsGeometry()
    elif flat_type == QgsWkbTypes.GeometryCollection or geometry.isMultipart():
        parts = []
        for part in geometry.constParts():
            part_geom = QgsGeometry(part.clone())
            clean_part = clean_and_remove_holes(part_geom, target_crs, remove_holes)
            if not clean_part.isEmpty():
                parts.append(clean_part)
        if parts:
            collected = QgsGeometry.collectGeometry(parts)
            return collected
        return QgsGeometry()
    return geometry


def clean_unsnapped_vertices(eas_list: List[dict], snap_tolerance: float, road_geoms: dict, river_geoms: dict, barangay_by_id: dict):
    idx_spatial = QgsSpatialIndex()
    ea_map = {}
    for idx_ea, ea_item in enumerate(eas_list):
        f_ea = QgsFeature(idx_ea)
        f_ea.setGeometry(ea_item['geom'])
        idx_spatial.insertFeature(f_ea)
        ea_map[idx_ea] = ea_item

    constraint_geoms = []
    for r in road_geoms.values():
        constraint_geoms.append(r)
    for r in river_geoms.values():
        constraint_geoms.append(r)
    for r in barangay_by_id.values():
        g_bar = r.geometry()
        if g_bar.isEmpty():
            continue
        flat_type_bar = QgsWkbTypes.flatType(g_bar.wkbType())
        if flat_type_bar == QgsWkbTypes.Polygon:
            for ring in g_bar.asPolygon():
                constraint_geoms.append(QgsGeometry.fromPolylineXY(ring))
        elif flat_type_bar == QgsWkbTypes.MultiPolygon:
            for part in g_bar.asMultiPolygon():
                for ring in part:
                    constraint_geoms.append(QgsGeometry.fromPolylineXY(ring))

    def lies_on_constraint(pt):
        pt_geom = QgsGeometry.fromPointXY(pt)
        for cg in constraint_geoms:
            if cg.distance(pt_geom) < 1e-7:
                return True
        return False

    modified = True
    iteration = 0
    max_iterations = 3

    while modified and iteration < max_iterations:
        modified = False
        iteration += 1

        for idx_ea, ea_item in ea_map.items():
            geom = ea_item['geom']
            if geom.isEmpty():
                continue

            flat_type = QgsWkbTypes.flatType(geom.wkbType())
            if flat_type not in (QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon):
                continue

            neighbor_ids = idx_spatial.intersects(geom.boundingBox())
            neighbors = [ea_map[nid]['geom'] for nid in neighbor_ids if nid != idx_ea and not ea_map[nid]['geom'].isEmpty()]
            if not neighbors:
                continue

            neighbor_vertices = set()
            for n_geom in neighbors:
                n_type = QgsWkbTypes.flatType(n_geom.wkbType())
                if n_type == QgsWkbTypes.Polygon:
                    p_list = [n_geom.asPolygon()]
                elif n_type == QgsWkbTypes.MultiPolygon:
                    p_list = n_geom.asMultiPolygon()
                else:
                    continue

                for part_pts in p_list:
                    for ring_pts in part_pts:
                        for pt_val in ring_pts:
                            neighbor_vertices.add((round(pt_val.x(), 8), round(pt_val.y(), 8)))

            if flat_type == QgsWkbTypes.Polygon:
                parts_list = [geom.asPolygon()]
            else:
                parts_list = geom.asMultiPolygon()

            polygon_changed = False
            new_parts = []

            for part_idx, part_pts in enumerate(parts_list):
                new_rings = []
                for ring_idx, ring_pts in enumerate(part_pts):
                    pts = list(ring_pts)
                    if len(pts) <= 4:
                        new_rings.append(pts)
                        continue

                    n_pts = len(pts) - 1
                    pt_idx = 0

                    while pt_idx < n_pts:
                        if len(pts) <= 4:
                            break

                        pt_val = pts[pt_idx]
                        pt_rounded = (round(pt_val.x(), 8), round(pt_val.y(), 8))

                        if pt_rounded in neighbor_vertices:
                            pt_idx += 1
                            continue

                        if lies_on_constraint(pt_val):
                            pt_idx += 1
                            continue

                        pt_geom = QgsGeometry.fromPointXY(pt_val)
                        min_dist = float('inf')
                        for n_geom in neighbors:
                            dist_val = n_geom.distance(pt_geom)
                            if dist_val < min_dist:
                                min_dist = dist_val

                        if not (0.0 < min_dist <= snap_tolerance):
                            pt_idx += 1
                            continue

                        candidate_pts = [p for idx_p, p in enumerate(pts) if idx_p != pt_idx]
                        if pt_idx == 0:
                            candidate_pts[-1] = candidate_pts[0]
                        elif pt_idx == n_pts - 1:
                            candidate_pts[0] = candidate_pts[-1]

                        test_parts = []
                        for p_p in new_parts:
                            test_parts.append(p_p)

                        current_test_rings = []
                        for r in new_rings:
                            current_test_rings.append(r)
                        current_test_rings.append(candidate_pts)
                        for r in part_pts[len(new_rings) + 1:]:
                            current_test_rings.append(r)
                        test_parts.append(current_test_rings)

                        for p_p in parts_list[len(new_parts) + 1:]:
                            test_parts.append(p_p)

                        if flat_type == QgsWkbTypes.Polygon:
                            temp_geom = QgsGeometry.fromPolygonXY(test_parts[0])
                        else:
                            temp_geom = QgsGeometry.fromMultiPolygonXY(test_parts)

                        if not temp_geom.isValid() or temp_geom.isEmpty():
                            pt_idx += 1
                            continue

                        buildings_lost = False
                        for b in ea_item.get('buildings', []):
                            b_geom = QgsGeometry.fromPointXY(b['point'])
                            if not (temp_geom.contains(b_geom) or temp_geom.intersects(b_geom)):
                                buildings_lost = True
                                break
                        if buildings_lost:
                            pt_idx += 1
                            continue

                        overlap_ok = True
                        for n_geom in neighbors:
                            old_overlap = geom.intersection(n_geom).area()
                            new_overlap = temp_geom.intersection(n_geom).area()
                            if new_overlap - old_overlap > 1e-9:
                                overlap_ok = False
                                break
                        if not overlap_ok:
                            pt_idx += 1
                            continue

                        pts = candidate_pts
                        n_pts = len(pts) - 1
                        polygon_changed = True
                        modified = True

                    new_rings.append(pts)
                new_parts.append(new_rings)

            if polygon_changed:
                if flat_type == QgsWkbTypes.Polygon:
                    ea_item['geom'] = QgsGeometry.fromPolygonXY(new_parts[0])
                else:
                    ea_item['geom'] = QgsGeometry.fromMultiPolygonXY(new_parts)

                idx_spatial.deleteFeature(idx_ea)
                f_ea = QgsFeature(idx_ea)
                f_ea.setGeometry(ea_item['geom'])
                idx_spatial.insertFeature(f_ea)


def run_phase_8(
    alg: Any,
    parameters: Dict[str, Any],
    context: Any,
    feedback: Any,
    multi_feedback: Any,
    p1: Dict[str, Any],
    p2: Dict[str, Any],
    p3: Dict[str, Any],
    p4: Dict[str, Any],
    p7: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Executes Phase 8: Spatial Sorting, Boundary Vertices Cleanup & Sink Feature Writing.
    """
    eas = list(p7["eas"])
    previous_ea_source = p1["previous_ea_source"]
    building_source = p1["building_source"]
    out_fields = p2.get("out_fields") or p1.get("out_fields")
    target_crs = p1["target_crs"]
    max_ea_number = p4.get("max_ea_number") if p4 else p1.get("max_ea_number", {})
    area_threshold = p1["area_threshold"]
    max_household = p1["max_household"]
    min_household = p1["min_household"]
    output_hh_field = p2.get("output_hh_field") or p1.get("output_hh_field", "household")
    bldg_hh_field = p1["bldg_hh_field"]
    ea_id_field = p1["ea_id_field"]
    barangay_by_id = p1["barangay_by_id"]

    delineation_candidate_ids = p2["delineation_candidate_ids"]
    merge_candidate_ids = p2["merge_candidate_ids"]
    adjacent_ea_ids = p2["adjacent_ea_ids"]

    road_geoms = p3["road_geoms"]
    river_geoms = p3["river_geoms"]

    # Sinks & Count trackers from p2 (or p1)
    delineated_sink = p2.get("delineated_sink") or p1.get("delineated_sink")
    merged_sink = p2.get("merged_sink") or p1.get("merged_sink")
    special_ea_sink = p2.get("special_ea_sink") or p1.get("special_ea_sink")
    extracted_buildings_sink = p2.get("extracted_buildings_sink") or p1.get("extracted_buildings_sink")

    delineated_feat_count = 0
    merged_feat_count = 0
    special_ea_feat_count = 0
    extracted_bldg_feat_count = 0

    delin_candidate_feat_count = p2.get("delin_candidate_feat_count", len(delineation_candidate_ids))
    merge_candidate_feat_count = p2.get("merge_candidate_feat_count", len(merge_candidate_ids | adjacent_ea_ids))

    # Post-Processing: Spatial Barangay Sorting & Code Assignment
    feedback.pushInfo("Post-processing: Spatially sorting EAs within parent barangays and assigning new_ea codes...")

    barangay_to_final_eas = {}
    for ea in eas:
        bar = ea['parent_barangay']
        if bar not in barangay_to_final_eas:
            barangay_to_final_eas[bar] = []
        barangay_to_final_eas[bar].append(ea)

    def get_sort_key(ea_item):
        centroid = ea_item['geom'].centroid().asPoint()
        return (centroid.x(), centroid.y())

    for bar in sorted(barangay_to_final_eas.keys(), key=lambda k: str(k) if k is not None else ""):
        bar_eas = barangay_to_final_eas[bar]
        has_delin = any(ea.get('original_id') in delineation_candidate_ids for ea in bar_eas)
        if has_delin:
            bar_eas.sort(key=get_sort_key)
        else:
            def get_original_order_key(ea_item):
                orig_id = ea_item.get('original_id', 99999999)
                centroid = ea_item['geom'].centroid().asPoint()
                return (orig_id, centroid.x())
            bar_eas.sort(key=get_original_order_key)

        new_ea_counter = 0
        for i, ea in enumerate(bar_eas):
            orig_last3 = "000"
            name_idx = out_fields.indexOf("name")
            if name_idx != -1 and ea['attributes'][name_idx] is not None:
                name_val = str(ea['attributes'][name_idx]).strip()
                digits = "".join([c for c in name_val if c.isdigit()])
                if len(digits) >= 3:
                    orig_last3 = digits[:3]
                elif len(digits) > 0:
                    orig_last3 = digits.zfill(3)

            if orig_last3 == "000" or not orig_last3.isdigit():
                orig_code_str = str(ea['original_code']).strip() if ea['original_code'] is not None else "000"
                if orig_code_str.endswith(".0"):
                    orig_code_str = orig_code_str[:-2]
                if len(orig_code_str) > 9:
                    suffix = orig_code_str[9:]
                else:
                    suffix = orig_code_str
                orig_last3 = suffix.zfill(3)
                if len(orig_last3) > 3:
                    orig_last3 = orig_last3[:3]

            if ea.get('is_new', False):
                seq_num = max_ea_number.get(bar, 0) + 1 + new_ea_counter
                seq_str = f"{seq_num:03d}"
                new_ea_counter += 1

                if orig_last3 == "000":
                    ea['new_ea_code'] = seq_str + "000"
                else:
                    ea['new_ea_code'] = orig_last3 + seq_str
            else:
                orig_code_str = str(ea['original_code']).strip() if ea['original_code'] is not None else ""
                if orig_code_str.endswith(".0"):
                    orig_code_str = orig_code_str[:-2]
                ea['new_ea_code'] = orig_code_str

            ea['new_ea_tracker'] = ea['new_ea_code']
            ea['sort_index'] = i

    # Phase 8: Output Generation & Writing
    multi_feedback.setCurrentStep(7)
    multi_feedback.setProgressText(f"{_PHASE_LABELS[7]} [0/{len(eas):,}]...")
    feedback.pushInfo("Phase 8/8: Writing output features...")

    source_crs = previous_ea_source.sourceCrs()
    v_tolerance = math.sqrt(area_threshold) * 0.1
    if source_crs.isGeographic():
        v_tolerance = max(1e-7, min(v_tolerance, 1e-5))
    else:
        v_tolerance = max(0.01, min(v_tolerance, 0.5))

    feedback.pushInfo("Cleaning up unsnapped vertices along shared boundaries...")
    clean_unsnapped_vertices(eas, v_tolerance, road_geoms, river_geoms, barangay_by_id)

    eas.sort(key=lambda ea: (
        str(ea.get('parent_barangay', '')) if ea.get('parent_barangay') is not None else '',
        ea.get('sort_index', 0)
    ))

    barangay_to_target = None
    if previous_ea_source.sourceCrs() != target_crs:
        feedback.pushInfo(f"Transforming output to {target_crs.authid()}...")
        barangay_to_target = QgsCoordinateTransform(
            previous_ea_source.sourceCrs(), target_crs, context.transformContext()
        )

    for i, ea in enumerate(eas):
        if multi_feedback.isCanceled():
            raise QgsProcessingException("Algorithm cancelled by user.")
        yield_to_ui(i, 50)

        geom = QgsGeometry(ea['geom'])
        if barangay_to_target:
            geom.transform(barangay_to_target)

        geom = geom.makeValid()

        poly_parts = get_polygons_from_geom(geom)
        if not poly_parts:
            feedback.pushWarning(
                f"[Output] EA (code={ea.get('original_code', '?')}, "
                f"pop={ea.get('hh_count', '?')}) has no polygon geometry after "
                f"filtering — skipping feature."
            )
            continue

        geom = poly_parts[0]
        for p in poly_parts[1:]:
            geom = geom.combine(p)
        geom = geom.buffer(0.0, 3)
        geom.convertToMultiType()

        is_unchanged_retain = False
        if not ea.get('from_split', False) and not ea.get('from_merge', False):
            _ea_id = ea.get('original_id')
            if _ea_id not in delineation_candidate_ids and _ea_id not in merge_candidate_ids:
                is_unchanged_retain = True

        geom = clean_and_remove_holes(geom, target_crs, remove_holes=(not is_unchanged_retain))

        simp_tolerance = 1e-7 if target_crs.isGeographic() else 0.01
        geom = geom.simplify(simp_tolerance)
        geom = geom.makeValid()

        out_feat = QgsFeature(out_fields)
        out_feat.setGeometry(geom)

        src_fields = previous_ea_source.fields()
        src_attrs = ea['attributes']
        mapped_attrs = []
        for f in out_fields:
            src_idx = src_fields.indexOf(f.name())
            if src_idx != -1 and src_idx < len(src_attrs):
                mapped_attrs.append(src_attrs[src_idx])
            else:
                mapped_attrs.append(None)
        out_feat.setAttributes(mapped_attrs)

        final_pop = ea['original_hhcount'] if is_unchanged_retain else ea['hh_count']

        pop_idx = out_fields.indexOf(output_hh_field)
        if pop_idx != -1:
            out_feat.setAttribute(pop_idx, final_pop)

        fid_idx = out_fields.indexOf("fid")
        if fid_idx != -1:
            out_feat.setAttribute(fid_idx, None)

        new_ea_idx = out_fields.indexOf("new_ea")
        if new_ea_idx != -1:
            out_feat.setAttribute(new_ea_idx, ea.get('new_ea_tracker'))

        bldg_count_idx = out_fields.indexOf("bldg_count")
        if bldg_count_idx != -1:
            out_feat.setAttribute(bldg_count_idx, ea.get('bldg_count', 0))

        hh_count_idx = out_fields.indexOf("hh_count")
        if hh_count_idx != -1:
            out_feat.setAttribute(hh_count_idx, final_pop)

        hhcount_idx = out_fields.indexOf("hhcount")
        if hhcount_idx != -1:
            out_feat.setAttribute(hhcount_idx, final_pop)

        bldgpts_val_idx = out_fields.indexOf("bldgpoints_value")
        if bldgpts_val_idx != -1:
            out_feat.setAttribute(bldgpts_val_idx, ea.get('bldgpoints_value', 0.0))

        split_by_idx = out_fields.indexOf("split_by")
        if split_by_idx != -1:
            out_feat.setAttribute(split_by_idx, ea.get('split_by', 'none'))

        ean_field_idx = out_fields.indexOf(ea_id_field)
        if ean_field_idx != -1 and ea_id_field.lower() != "geocode":
            out_feat.setAttribute(ean_field_idx, ea['new_ea_code'])

        ea_type_idx = out_fields.indexOf("ea_type")
        if ea_type_idx != -1:
            out_feat.setAttribute(ea_type_idx, ea.get('ea_type', 'STANDARD'))

        special_type_idx = out_fields.indexOf("special_type")
        if special_type_idx != -1:
            out_feat.setAttribute(special_type_idx, ea.get('special_type', None))

        source_id_idx = out_fields.indexOf("source_id")
        if source_id_idx != -1:
            out_feat.setAttribute(source_id_idx, ea.get('source_id', None))

        remarks_idx = out_fields.indexOf("remarks")
        if remarks_idx != -1:
            out_feat.setAttribute(remarks_idx, ea.get('remarks', None))

        corr_ea_geo_idx = out_fields.indexOf("correspondence_ea_geocode")
        if corr_ea_geo_idx != -1:
            map_uuid_idx = out_fields.indexOf("map_uuid")
            geocode_idx = out_fields.indexOf("geocode")
            sy_idx = out_fields.indexOf("sy")

            map_uuid_val = out_feat.attribute(map_uuid_idx) if map_uuid_idx != -1 else ""
            geocode_val = out_feat.attribute(geocode_idx) if geocode_idx != -1 else ""
            sy_val = out_feat.attribute(sy_idx) if sy_idx != -1 else ""

            map_uuid_str = str(map_uuid_val) if map_uuid_val is not None else ""
            geocode_str = str(geocode_val) if geocode_val is not None else ""
            sy_str = str(sy_val) if sy_val is not None else ""

            if map_uuid_str.endswith(".0"):
                map_uuid_str = map_uuid_str[:-2]
            if geocode_str.endswith(".0"):
                geocode_str = geocode_str[:-2]
            if sy_str.endswith(".0"):
                sy_str = sy_str[:-2]

            concat_val = f"{map_uuid_str}:{geocode_str}:{sy_str}"
            out_feat.setAttribute(corr_ea_geo_idx, concat_val)

        # Explicitly set eadel_indi indicator field
        eadel_indi_out_idx = out_fields.indexOf("eadel_indi")
        if eadel_indi_out_idx != -1:
            _ea_id_tmp = ea.get('original_id')
            is_delin_feat = (_ea_id_tmp in delineation_candidate_ids) or ea.get('from_split', False)
            out_feat.setAttribute(eadel_indi_out_idx, "for_delineation" if is_delin_feat else "ea_reference")

        # Check if EA feature is blank (empty geometry or missing geocode/ean identifiers)
        _gc_val = out_feat.attribute(out_fields.indexOf("geocode")) if out_fields.indexOf("geocode") != -1 else None
        _ean_val = out_feat.attribute(out_fields.indexOf(ea_id_field)) if out_fields.indexOf(ea_id_field) != -1 else None
        _is_blank_feat = out_feat.geometry().isEmpty() or (
            (_gc_val is None or (isinstance(_gc_val, QVariant) and _gc_val.isNull()) or str(_gc_val).strip() in ('', 'NULL', 'None'))
            and (_ean_val is None or (isinstance(_ean_val, QVariant) and _ean_val.isNull()) or str(_ean_val).strip() in ('', 'NULL', 'None'))
        )

        if _is_blank_feat:
            feedback.pushWarning(f"[Output] Skipped writing blank EA feature to output layer (code={ea.get('original_code', '?')}).")
        else:
            _ea_id = ea.get('original_id')
            # Add to Special EAs sink if it is a Special EA (Gap/Overlap)
            if ea.get('is_special_ea', False):
                if special_ea_sink is not None:
                    if special_ea_sink.addFeature(out_feat, QgsFeatureSink.Flag.FastInsert):
                        special_ea_feat_count += 1
                    else:
                        feedback.reportError(f"Failed to add Special EA {i} to special EA sink.")
            # Add to delineated sink if it was split and not a Special EA
            elif ea.get('from_split', False):
                if delineated_sink is not None:
                    if delineated_sink.addFeature(out_feat, QgsFeatureSink.Flag.FastInsert):
                        delineated_feat_count += 1
                    else:
                        feedback.reportError(f"Failed to add EA {i} to delineated sink.")

            # Add to merged sink if it was merged, not split, not Special EA, and has >0 hh_count and >0 bldg_count
            if ea.get('from_merge', False) and not ea.get('from_split', False) and not ea.get('is_special_ea', False):
                if merged_sink is not None:
                    _m_hh = ea.get('hh_count', 0.0)
                    _m_bldg = ea.get('bldg_count', 0)
                    if _m_hh > 0 and _m_bldg > 0:
                        if merged_sink.addFeature(out_feat, QgsFeatureSink.Flag.FastInsert):
                            merged_feat_count += 1
                        else:
                            feedback.reportError(f"Failed to add EA {i} to merged sink.")
                    else:
                        feedback.pushWarning(
                            f"[Merged Output] Skipped writing zero-count merged EA (code={ea.get('original_code', '?')}, "
                            f"hh_count={_m_hh}, bldg_count={_m_bldg}) to merged sink."
                        )

        # Add matched buildings to extracted buildings sink
        if extracted_buildings_sink is not None:
            bldg_out_fields = QgsFields(building_source.fields())
            if bldg_out_fields.indexOf("parent_ean") == -1:
                bldg_out_fields.append(QgsField("parent_ean", QVariant.String))

            bldgpts_idx = bldg_out_fields.indexOf("bldgpoints_value")
            if bldgpts_idx == -1:
                bldgpts_idx = bldg_out_fields.indexOf("bldgpts_val")
            if bldgpts_idx == -1:
                bldg_out_fields.append(QgsField("bldgpoints_value", QVariant.Double))
                bldgpts_idx = bldg_out_fields.count() - 1

            pop_out_idx = bldg_out_fields.indexOf("pop")
            if pop_out_idx == -1:
                pop_out_idx = bldg_out_fields.indexOf(bldg_hh_field)
            if pop_out_idx == -1:
                bldg_out_fields.append(QgsField("pop", QVariant.Double))
                pop_out_idx = bldg_out_fields.count() - 1

            parent_ean_idx = bldg_out_fields.indexOf("parent_ean")

            _ea_orig_id = ea.get('original_id')
            _ea_orig_code = ea.get('original_code', '')
            parent_ean_val = ea.get('new_ea_code', _ea_orig_code)
            _is_target_ea = (
                ea.get('from_split', False)
                or ea.get('from_merge', False)
                or _ea_orig_id in delineation_candidate_ids
                or _ea_orig_id in merge_candidate_ids
                or _ea_orig_id in adjacent_ea_ids
            )
            if _is_target_ea:
                for b in ea.get('buildings', []):
                    b_feat = QgsFeature(bldg_out_fields)
                    b_geom = QgsGeometry.fromPointXY(b['point'])
                    if barangay_to_target:
                        b_geom.transform(barangay_to_target)
                    b_feat.setGeometry(b_geom)

                    b_attrs = list(b['attributes']) if 'attributes' in b else []
                    needed = bldg_out_fields.count() - len(b_attrs)
                    if needed > 0:
                        b_attrs.extend([None] * needed)
                    elif len(b_attrs) > bldg_out_fields.count():
                        b_attrs = b_attrs[:bldg_out_fields.count()]

                    if bldgpts_idx != -1:
                        b_attrs[bldgpts_idx] = b['bldgpoints_value']
                    if pop_out_idx != -1:
                        b_attrs[pop_out_idx] = b['pop']
                    if parent_ean_idx != -1:
                        b_attrs[parent_ean_idx] = str(parent_ean_val)

                    b_feat.setAttributes(b_attrs)
                    if extracted_buildings_sink.addFeature(b_feat, QgsFeatureSink.Flag.FastInsert):
                        extracted_bldg_feat_count += 1
                    else:
                        feedback.reportWarning("Failed to add building point to extracted buildings sink.")

        _out_pct = int((i + 1) / max(len(eas), 1) * 100)
        multi_feedback.setProgress(_out_pct)
        if i % 100 == 0 or _out_pct == 100:
            multi_feedback.setProgressText(
                f"{_PHASE_LABELS[7]} [{i + 1:,}/{len(eas):,}]..."
            )

    multi_feedback.setProgress(100)
    feedback.pushInfo("Successfully created and structured Enumeration Areas.")

    total_proc = getattr(alg, 'total_ea_processed', 0)
    total_cand = getattr(alg, 'total_delin_candidates', 0)
    feedback.pushInfo("--------------------------------------------------")
    feedback.pushInfo(f"Total number of EAs processed: {total_proc}")
    feedback.pushInfo(f"Total number of delineation candidates identified (hhcount >= {max_household}): {total_cand}")

    if total_cand == 0 and delineated_feat_count == 0:
        delin_remark = f"No EAs exceeded {max_household} HH threshold or intersected Gap/Overlap layers."
    else:
        delin_remark = f"Processed {total_cand} candidate(s) into {delineated_feat_count} delineated sub-EA(s)."

    init_cand_cnt = len(merge_candidate_ids)
    if merged_feat_count == 0:
        if merge_candidate_feat_count > 0:
            merge_remark = f"Identified {init_cand_cnt} candidate(s) (under {min_household} HH), but 0 merged. Reason: Candidates have no valid adjacent neighbors within same Barangay (single-EA barangays or combined HH > {max_household})."
        else:
            merge_remark = f"No under-threshold EAs (under {min_household} HH) required merging."
    else:
        merge_remark = f"Successfully created {merged_feat_count} merged EA polygon(s)."

    adj_partner_cnt = max(0, merge_candidate_feat_count - init_cand_cnt)
    if adj_partner_cnt > 0:
        merge_cand_desc = f"{init_cand_cnt} initiator EA(s) (under {min_household} HH) + {adj_partner_cnt} adjacent reference neighbor(s)"
    else:
        merge_cand_desc = f"Initiator EAs (under {min_household} HH)"

    html_table = (
        "<html_table>"
        "<br/><b>Execution Results &amp; Output Summary</b>"
        "<table border='1' cellspacing='0' cellpadding='6' style='border-collapse:collapse; width:100%; margin:8px 0; font-family:sans-serif; font-size:11px;'>"
        "<tr style='background-color:#2d3748; color:#ffffff; font-weight:bold;'>"
        "<th align='left'>Output Layer</th>"
        "<th align='center'>Feature Count</th>"
        "<th align='left'>Execution Remark / Status</th>"
        "</tr>"
        f"<tr><td><b>Delineated EAs</b></td><td align='center'><b>{delineated_feat_count:,}</b></td><td>{delin_remark}</td></tr>"
        f"<tr><td><b>Merged EAs</b></td><td align='center'><b>{merged_feat_count:,}</b></td><td>{merge_remark}</td></tr>"
        f"<tr><td><b>Special EAs</b></td><td align='center'><b>{special_ea_feat_count:,}</b></td><td>EAs generated from Gap/Overlap polygon layers</td></tr>"
        f"<tr><td><b>Delineation Candidates</b></td><td align='center'>{delin_candidate_feat_count:,}</td><td>EAs exceeding {max_household} HH threshold or in Gap/Overlap layers</td></tr>"
        f"<tr><td><b>Merge Candidates</b></td><td align='center'>{merge_candidate_feat_count:,}</td><td>{merge_cand_desc}</td></tr>"
        f"<tr><td><b>Extracted Building Points</b></td><td align='center'>{extracted_bldg_feat_count:,}</td><td>Building points extracted inside candidate EAs</td></tr>"
        "</table>"
        "</html_table>"
    )

    feedback.pushInfo(html_table)
    feedback.pushInfo("--------------------------------------------------")
    feedback.pushInfo("Completed.")

    return p2.get("outputs") or p1.get("outputs", {})
