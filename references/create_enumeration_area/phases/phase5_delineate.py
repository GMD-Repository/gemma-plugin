import math
import time
import concurrent.futures
from typing import Dict, Any, List

from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsSpatialIndex,
    QgsProcessingException,
)
from qgis.PyQt.QtCore import QCoreApplication, QThread

from ..helpers.constants import _PHASE_LABELS
from ..helpers.geometry import (
    get_polygons_from_geom,
    allocate_gaps_to_parts,
    collect_linear_features,
    merge_line_geometries,
    weighted_kmeans,
)


def force_geometric_split(ea_item, target_pop, fback, min_household=100, max_household=300):
    hh_cnt = ea_item['hh_count']
    bldgs = ea_item.get('buildings', [])
    bbox = ea_item['geom'].boundingBox()

    def make_strips(n, horizontal):
        strips = []
        for i in range(n):
            if horizontal:
                span = bbox.height() / n
                y0 = bbox.yMinimum() + i * span
                y1 = bbox.yMinimum() + (i + 1) * span
                pts = [
                    QgsPointXY(bbox.xMinimum(), y0),
                    QgsPointXY(bbox.xMaximum(), y0),
                    QgsPointXY(bbox.xMaximum(), y1),
                    QgsPointXY(bbox.xMinimum(), y1),
                    QgsPointXY(bbox.xMinimum(), y0),
                ]
            else:
                span = bbox.width() / n
                x0 = bbox.xMinimum() + i * span
                x1 = bbox.xMinimum() + (i + 1) * span
                pts = [
                    QgsPointXY(x0, bbox.yMinimum()),
                    QgsPointXY(x1, bbox.yMinimum()),
                    QgsPointXY(x1, bbox.yMaximum()),
                    QgsPointXY(x0, bbox.yMaximum()),
                    QgsPointXY(x0, bbox.yMinimum()),
                ]
            strip_geom = QgsGeometry.fromPolygonXY([pts])
            intersected = ea_item['geom'].intersection(strip_geom)
            if not intersected.isEmpty():
                strips.extend(get_polygons_from_geom(intersected))
        return strips

    use_horizontal = bbox.height() >= bbox.width()
    k_start = max(2, math.ceil(hh_cnt / float(target_pop if target_pop > 0 else 200)))
    k_max = k_start + 4

    accepted_parts = None
    accepted_k = None
    accepted_orientation = use_horizontal

    for k_val in range(k_start, k_max + 1):
        strip_polys = make_strips(k_val, horizontal=use_horizontal)
        orientation = 'horizontal'
        if len(strip_polys) < 2:
            strip_polys = make_strips(k_val, horizontal=not use_horizontal)
            orientation = 'vertical'

        if len(strip_polys) < 2:
            break

        parts = []
        for poly in strip_polys:
            buildings_in_poly = []
            for b in bldgs:
                pt_geom = QgsPointXY(b['point'])
                if poly.contains(QgsGeometry.fromPointXY(pt_geom)) or poly.intersects(QgsGeometry.fromPointXY(pt_geom)):
                    buildings_in_poly.append(b)
            sub_pop = sum(b['pop'] for b in buildings_in_poly)
            parts.append({
                'geom': poly,
                'buildings': buildings_in_poly,
                'hh_count': sub_pop,
                'original_hhcount': ea_item.get('original_hhcount', 0),
                'bldg_count': len(buildings_in_poly),
                'bldgpoints_value': sub_pop / len(buildings_in_poly) if len(buildings_in_poly) > 0 else 0.0,
                'attributes': list(ea_item['attributes']),
                'original_id': ea_item['original_id'],
                'original_code': ea_item['original_code'],
                'is_new': True,
                'from_split': True,
                'split_by': 'forced_grid',
                'parent_barangay': ea_item['parent_barangay']
            })

        zero_parts = [p for p in parts if p['hh_count'] == 0]
        nonzero_parts = [p for p in parts if p['hh_count'] > 0]

        if not nonzero_parts:
            continue

        for zp in zero_parts:
            zp_centroid = zp['geom'].centroid().asPoint()
            best_nb = min(
                nonzero_parts,
                key=lambda np: zp_centroid.distance(np['geom'].centroid().asPoint())
            )
            raw_combined = best_nb['geom'].combine(zp['geom']).buffer(0.0, 3)
            clipped = raw_combined.intersection(ea_item['geom'])
            best_nb['geom'] = clipped if not clipped.isEmpty() else raw_combined
            best_nb['buildings'].extend(zp['buildings'])
            best_nb['bldg_count'] = len(best_nb['buildings'])

        parts = nonzero_parts
        if len(parts) < 2:
            continue

        all_valid = all(p['hh_count'] <= max_household for p in parts)

        if accepted_parts is None or all_valid:
            accepted_parts = parts
            accepted_k = k_val
            accepted_orientation = orientation

        if all_valid:
            break

    if accepted_parts is None:
        fback.pushWarning(
            f"[EA {ea_item['original_code']}] FORCED SPLIT: Could not produce >= 2 valid "
            f"parts at any k ({k_start}–{k_max}). EA will remain over threshold."
        )
        return [ea_item]

    final_parts = []
    for part in accepted_parts:
        if part['hh_count'] > max_household:
            if part.get('from_merge', False):
                final_parts.append(part)
                continue
            sub_result = force_geometric_split(part, target_pop, fback, min_household, max_household)
            if len(sub_result) > 1:
                final_parts.extend(sub_result)
            else:
                final_parts.append(part)
        else:
            final_parts.append(part)

    orig_code_str = str(ea_item['original_code']).strip() if ea_item['original_code'] is not None else "000"
    digits = "".join([c for c in orig_code_str if c.isdigit()])
    orig_first3 = digits[:3] if len(digits) >= 3 else digits.zfill(3)
    if orig_first3 != "000" and len(final_parts) > 0:
        final_parts.sort(key=lambda x: x['hh_count'], reverse=True)
        final_parts[0]['is_new'] = False

    final_parts = allocate_gaps_to_parts(final_parts, ea_item['geom'])

    parent_geom = ea_item['geom']
    for p in final_parts:
        clipped = p['geom'].intersection(parent_geom).buffer(0.0, 3)
        if not clipped.isEmpty():
            p['geom'] = clipped

    fback.pushWarning(
        f"[EA {ea_item['original_code']}] FORCED SPLIT: Applied {accepted_orientation} "
        f"strip split (k={accepted_k}) — EA (hh_count={hh_cnt}) → {len(final_parts)} part(s)."
    )
    return final_parts


def run_phase_5(alg, parameters, context, feedback, multi_feedback, p1, p2, p3, p4):
    """

    Executes Phase 5 (Iterative Per-Barangay Delineation / EA Splitting).

    Returns dictionary containing:
    - split_eas: List[dict] of EAs after iterative splitting
    """
    eadel_indi_col_idx = p1["eadel_indi_col_idx"]
    full_ea_by_id = p2["full_ea_by_id"]
    min_household = p1["min_household"]
    max_household = p1["max_household"]
    target_household = p1["target_household"]
    snap_tolerance = p1["snap_tolerance"]
    densify_dist = p1["densify_dist"]
    area_threshold = p1["area_threshold"]
    num_cores = p1.get("num_cores", QThread.idealThreadCount())

    delineation_candidate_ids = p2["delineation_candidate_ids"]
    merge_candidate_ids = p2["merge_candidate_ids"]
    delineation_candidate_hhdivthres = p2["delineation_candidate_hhdivthres"]

    road_index = p3["road_index"]
    road_geoms = p3["road_geoms"]
    river_index = p3["river_index"]
    river_geoms = p3["river_geoms"]

    eas = p4["eas"]

    def is_parent_delineation_candidate(ea_item):
        orig_id = ea_item.get('original_id')
        if orig_id is not None and eadel_indi_col_idx != -1 and orig_id in full_ea_by_id:
            val = full_ea_by_id[orig_id].attribute(eadel_indi_col_idx)
            return val is not None and str(val).strip().lower() in ("for delineation", "for_delineation")
        return False

    def is_delineation_candidate(ea_item):
        if ea_item.get('from_split', False) or ea_item.get('from_merge', False):
            return False
        orig_id = ea_item.get('original_id')
        is_explicit = False
        if eadel_indi_col_idx != -1 and orig_id in full_ea_by_id:
            val = full_ea_by_id[orig_id].attribute(eadel_indi_col_idx)
            is_explicit = (val is not None and str(val).strip().lower() in ("for delineation", "for_delineation"))
        return is_explicit or (orig_id in delineation_candidate_ids) or (ea_item['hh_count'] >= max_household)

    def is_merge_candidate(ea_item):
        if ea_item.get('from_split', False):
            return ea_item['hh_count'] <= min_household
        if ea_item.get('from_merge', False):
            return False
        orig_id = ea_item.get('original_id')
        return (orig_id in merge_candidate_ids) or (ea_item['hh_count'] <= min_household)

    def enforce_min_household(parts, fback, ea_geom=None):
        is_parent_delin = False
        if parts:
            is_parent_delin = is_parent_delineation_candidate(parts[0])
        while len(parts) > 1:
            if is_parent_delin and len(parts) == 2:
                break
            under = [i for i, p in enumerate(parts) if p['hh_count'] <= min_household]
            if not under:
                break
            under.sort(key=lambda i: parts[i]['hh_count'])
            up_idx = under[0]
            up = parts[up_idx]

            best_idx = -1
            best_overlap = -1.0
            for j, nb in enumerate(parts):
                if j == up_idx:
                    continue
                if is_delineation_candidate(nb):
                    continue
                if up['geom'].intersects(nb['geom']) or up['geom'].touches(nb['geom']):
                    inter = up['geom'].intersection(nb['geom'])
                    overlap = inter.length() if not inter.isEmpty() else 0.0
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_idx = j

            if best_idx == -1:
                up_centroid = up['geom'].centroid().asPoint()
                best_dist = float('inf')
                best_dist_over = float('inf')
                best_idx_over = -1
                for j, nb in enumerate(parts):
                    if j == up_idx:
                        continue
                    if is_delineation_candidate(nb):
                        continue
                    dist = up_centroid.distance(nb['geom'].centroid().asPoint())
                    combined = up['hh_count'] + nb['hh_count']
                    if combined <= max_household:
                        if dist < best_dist:
                            best_dist = dist
                            best_idx = j
                    else:
                        if dist < best_dist_over:
                            best_dist_over = dist
                            best_idx_over = j
                if best_idx == -1:
                    best_idx = best_idx_over

            if best_idx == -1:
                break

            nb = parts[best_idx]
            raw_combined = nb['geom'].combine(up['geom']).buffer(0.0, 3)
            if ea_geom is not None:
                clipped = raw_combined.intersection(ea_geom).buffer(0.0, 3)
                nb['geom'] = clipped if not clipped.isEmpty() else raw_combined
            else:
                nb['geom'] = raw_combined
            nb['buildings'].extend(up['buildings'])
            nb['hh_count'] += up['hh_count']
            nb['bldg_count'] = len(nb['buildings'])
            parts.pop(up_idx)
        return parts

    def enforce_bldgpv_threshold(parts, hhdivthres, fback, ea_geom=None):
        while len(parts) > 1:
            parts_with_pv = []
            for idx, p in enumerate(parts):
                pv = sum(b.get('bldgpoints_value', 0.0) for b in p['buildings'])
                parts_with_pv.append((idx, pv))

            parts_with_pv.sort(key=lambda x: x[1], reverse=True)
            _max_bldgpv = parts_with_pv[0][1]

            if _max_bldgpv < hhdivthres:
                break

            up_idx = parts_with_pv[0][0]
            up = parts[up_idx]

            best_idx = -1
            best_overlap = -1.0
            for j, nb in enumerate(parts):
                if j == up_idx:
                    continue
                if up['geom'].intersects(nb['geom']) or up['geom'].touches(nb['geom']):
                    inter = up['geom'].intersection(nb['geom'])
                    overlap = inter.length() if not inter.isEmpty() else 0.0
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_idx = j

            if best_idx == -1:
                up_centroid = up['geom'].centroid().asPoint()
                best_dist = float('inf')
                for j, nb in enumerate(parts):
                    if j == up_idx:
                        continue
                    dist = up_centroid.distance(nb['geom'].centroid().asPoint())
                    if dist < best_dist:
                        best_dist = dist
                        best_idx = j

            if best_idx == -1:
                for j, nb in enumerate(parts):
                    if j != up_idx:
                        best_idx = j
                        break

            if best_idx == -1:
                break

            nb = parts[best_idx]
            raw_combined = nb['geom'].combine(up['geom']).buffer(0.0, 3)
            if ea_geom is not None:
                clipped = raw_combined.intersection(ea_geom).buffer(0.0, 3)
                nb['geom'] = clipped if not clipped.isEmpty() else raw_combined
            else:
                nb['geom'] = raw_combined

            nb['buildings'].extend(up['buildings'])
            nb['hh_count'] += up['hh_count']
            nb['bldg_count'] = len(nb['buildings'])

            parts.pop(up_idx)

        return parts

    def split_ea_voronoi(ea_item, target_pop, fback, split_by='none'):
        if fback.isCanceled():
            return [ea_item]
        bldgs = ea_item.get('buildings', [])
        if not bldgs:
            fback.pushWarning(f"[EA {ea_item['original_code']}] DIAGNOSTIC: Split skipped — no building points matched to this EA.")
            return [ea_item]

        coord_to_pt = {}
        for b in bldgs:
            pt = b['point']
            coord_to_pt[(pt.x(), pt.y())] = pt
        unique_pts = list(coord_to_pt.values())

        if len(unique_pts) < 2:
            fback.pushWarning(f"[EA {ea_item['original_code']}] DIAGNOSTIC: Split skipped — only {len(unique_pts)} unique building point(s). Need at least 2 unique locations to generate Voronoi.")
            ea_item['split_by'] = split_by
            return [ea_item]

        hh_cnt = sum(b['pop'] for b in bldgs)
        k_val = max(2, int(round(hh_cnt / float(max_household))))
        k_val = min(k_val, len(unique_pts))
        if k_val < 2:
            ea_item['split_by'] = split_by
            return [ea_item]

        _OUTLIER_FACTOR = 3.0
        kmeans_pts = unique_pts

        if len(unique_pts) >= 6:
            _local_idx = QgsSpatialIndex()
            for _i_pt, _q_pt in enumerate(unique_pts):
                _pf = QgsFeature(_i_pt)
                _pf.setGeometry(QgsGeometry.fromPointXY(_q_pt))
                _local_idx.insertFeature(_pf)

            _nn_dists = []
            for _i_pt, _q_pt in enumerate(unique_pts):
                _neighbors = _local_idx.nearestNeighbor(_q_pt, 2)
                _nn_d = float('inf')
                for _n_id in _neighbors:
                    if _n_id != _i_pt:
                        _n_pt = unique_pts[_n_id]
                        _nn_d = math.hypot(_q_pt.x() - _n_pt.x(), _q_pt.y() - _n_pt.y())
                        break
                _nn_dists.append(_nn_d)

            _sorted_d = sorted(d for d in _nn_dists if d < float('inf'))
            if _sorted_d:
                _median_nn = _sorted_d[len(_sorted_d) // 2]
                if _median_nn > 0:
                    _outlier_thr = _OUTLIER_FACTOR * _median_nn
                    _core = [q for q, d in zip(unique_pts, _nn_dists) if d <= _outlier_thr]
                    _n_outliers = sum(1 for d in _nn_dists if d > _outlier_thr)
                    if _n_outliers > 0 and len(_core) >= 2:
                        fback.pushInfo(
                            f"[EA {ea_item['original_code']}] Outlier filter: "
                            f"{_n_outliers} isolated building location(s) excluded from "
                            f"K-Means (NN dist > {_outlier_thr:.6f}, median={_median_nn:.6f}). "
                            f"Will be assigned via Voronoi containment after split."
                        )
                        kmeans_pts = _core

        k_val = min(k_val, len(kmeans_pts))
        if k_val < 2:
            kmeans_pts = unique_pts
            k_val = min(max(2, int(round(hh_cnt / float(target_pop)))), len(unique_pts))
            if k_val < 2:
                ea_item['split_by'] = split_by
                return [ea_item]

        pts = [(pt.x(), pt.y()) for pt in kmeans_pts]
        pt_to_weight = {}
        for b in bldgs:
            pt_key = (b['point'].x(), b['point'].y())
            pt_to_weight[pt_key] = pt_to_weight.get(pt_key, 0.0) + b['pop']
        wts = [pt_to_weight.get((pt.x(), pt.y()), 1.0) for pt in kmeans_pts]

        labels, centroids = weighted_kmeans(pts, wts, k_val)

        centroid_pts = [QgsPointXY(c[0], c[1]) for c in centroids]
        points_geom = QgsGeometry.fromMultiPointXY(centroid_pts)

        bbox = ea_item['geom'].boundingBox()
        buffer_size = max(0.01, max(bbox.width(), bbox.height()) * 0.2)
        extent_geom = QgsGeometry.fromRect(bbox.buffered(buffer_size))

        voronoi_geom = points_geom.voronoiDiagram(extent_geom)
        if voronoi_geom.isEmpty():
            ea_item['split_by'] = split_by
            return [ea_item]

        cells = get_polygons_from_geom(voronoi_geom)
        if not cells:
            ea_item['split_by'] = split_by
            return [ea_item]

        road_lines = collect_linear_features(ea_item['geom'], road_index, road_geoms)
        river_lines = collect_linear_features(ea_item['geom'], river_index, river_geoms)
        all_lines = road_lines + river_lines
        if all_lines:
            from qgis.analysis import QgsGeometrySnapper
            line_index = QgsSpatialIndex()
            line_map = {}
            for l_idx, line in enumerate(all_lines):
                feat = QgsFeature(l_idx)
                feat.setGeometry(line)
                line_index.insertFeature(feat)
                line_map[l_idx] = line

            snapped_cells = []
            for cell_geom in cells:
                buffered_bbox = cell_geom.boundingBox().buffered(snap_tolerance)
                candidate_line_ids = line_index.intersects(buffered_bbox)

                if not candidate_line_ids:
                    snapped_cells.append(cell_geom)
                    continue

                nearby_lines = [line_map[lid] for lid in candidate_line_ids]

                densified_cell = cell_geom.densifyByDistance(densify_dist)
                snapped_cell = QgsGeometrySnapper.snapGeometry(
                    densified_cell,
                    snap_tolerance,
                    nearby_lines,
                    QgsGeometrySnapper.PreferClosest
                )
                clean_snapped_cell = snapped_cell.buffer(0.0, 3)
                if clean_snapped_cell and not clean_snapped_cell.isEmpty():
                    snapped_cells.append(clean_snapped_cell)
                else:
                    snapped_cells.append(cell_geom)
            cells = snapped_cells

        split_parts = []
        sliver_filtered_bldgs = 0
        for cell_geom in cells:
            intersected = ea_item['geom'].intersection(cell_geom)
            if not intersected.isEmpty():
                polys = get_polygons_from_geom(intersected)
                for poly in polys:
                    buildings_in_poly = []
                    for b in bldgs:
                        pt_geom = QgsGeometry.fromPointXY(b['point'])
                        if poly.contains(pt_geom) or poly.intersects(pt_geom):
                            buildings_in_poly.append(b)
                    sub_pop = sum(b['pop'] for b in buildings_in_poly)
                    split_parts.append({
                        'geom': poly,
                        'buildings': buildings_in_poly,
                        'hh_count': sub_pop,
                        'original_hhcount': ea_item.get('original_hhcount', 0),
                        'bldg_count': len(buildings_in_poly),
                        'bldgpoints_value': sub_pop / len(buildings_in_poly) if len(buildings_in_poly) > 0 else 0.0,
                        'attributes': list(ea_item['attributes']),
                        'original_id': ea_item['original_id'],
                        'original_code': ea_item['original_code'],
                        'is_new': True,
                        'from_split': True,
                        'split_by': split_by,
                        'parent_barangay': ea_item['parent_barangay']
                    })
            elif not intersected.isEmpty():
                for b in bldgs:
                    pt_geom = QgsGeometry.fromPointXY(b['point'])
                    if intersected.contains(pt_geom) or intersected.intersects(pt_geom):
                        sliver_filtered_bldgs += 1

        if sliver_filtered_bldgs > 0:
            fback.pushWarning(
                f"[EA {ea_item['original_code']}] DIAGNOSTIC: Sliver threshold ({area_threshold:.2e}) caused {sliver_filtered_bldgs} building(s) "
                f"to be discarded in filtered-out cells. These buildings will be reassigned to surviving neighbours but may cause "
                f"a surviving part to exceed max_household ({max_household}). Consider lowering the sliver threshold."
            )

        zero_parts = [p for p in split_parts if p['hh_count'] == 0]
        nonzero_parts = [p for p in split_parts if p['hh_count'] > 0]

        if not nonzero_parts:
            ea_item['split_by'] = split_by
            return [ea_item]

        progress = True
        while zero_parts and progress:
            progress = False
            remaining_zero = []
            for zp in zero_parts:
                best_neighbor = None
                best_overlap = -1.0
                for np in nonzero_parts:
                    if zp['geom'].intersects(np['geom']) or zp['geom'].touches(np['geom']):
                        inter = zp['geom'].intersection(np['geom'])
                        overlap = inter.length() if not inter.isEmpty() else 0.0
                        if overlap > best_overlap:
                            best_overlap = overlap
                            best_neighbor = np
                if best_neighbor is not None:
                    raw_combined = best_neighbor['geom'].combine(zp['geom']).buffer(0.0, 3)
                    clipped = raw_combined.intersection(ea_item['geom']).buffer(0.0, 3)
                    best_neighbor['geom'] = clipped if not clipped.isEmpty() else raw_combined
                    best_neighbor['buildings'].extend(zp['buildings'])
                    best_neighbor['bldg_count'] = len(best_neighbor['buildings'])
                    progress = True
                else:
                    remaining_zero.append(zp)
            zero_parts = remaining_zero

        for zp in zero_parts:
            zp_centroid = zp['geom'].centroid().asPoint()
            best_neighbor = min(
                nonzero_parts,
                key=lambda np: zp_centroid.distance(np['geom'].centroid().asPoint())
            )
            raw_combined = best_neighbor['geom'].combine(zp['geom']).buffer(0.0, 3)
            clipped = raw_combined.intersection(ea_item['geom']).buffer(0.0, 3)
            best_neighbor['geom'] = clipped if not clipped.isEmpty() else raw_combined
            best_neighbor['buildings'].extend(zp['buildings'])
            best_neighbor['bldg_count'] = len(best_neighbor['buildings'])

        split_parts = nonzero_parts
        split_parts = enforce_min_household(split_parts, fback, ea_geom=ea_item['geom'])

        if len(split_parts) < 2:
            ea_item['split_by'] = split_by
            return [ea_item]

        orig_code_str = str(ea_item['original_code']).strip() if ea_item['original_code'] is not None else "000"
        digits = "".join([c for c in orig_code_str if c.isdigit()])
        orig_first3 = digits[:3] if len(digits) >= 3 else digits.zfill(3)

        if orig_first3 != "000" and len(split_parts) > 0:
            split_parts.sort(key=lambda x: x['hh_count'], reverse=True)
            split_parts[0]['is_new'] = False

        parent_geom = ea_item['geom']
        for p in split_parts:
            clipped = p['geom'].intersection(parent_geom).buffer(0.0, 3)
            if not clipped.isEmpty():
                p['geom'] = clipped
        split_parts = allocate_gaps_to_parts(split_parts, parent_geom)
        return split_parts

    def force_geometric_split(ea_item, target_pop, fback):
        hh_cnt = ea_item['hh_count']
        bldgs = ea_item.get('buildings', [])
        bbox = ea_item['geom'].boundingBox()

        def make_strips(n, horizontal):
            strips = []
            for i in range(n):
                if horizontal:
                    span = bbox.height() / n
                    y0 = bbox.yMinimum() + i * span
                    y1 = bbox.yMinimum() + (i + 1) * span
                    pts = [
                        QgsPointXY(bbox.xMinimum(), y0),
                        QgsPointXY(bbox.xMaximum(), y0),
                        QgsPointXY(bbox.xMaximum(), y1),
                        QgsPointXY(bbox.xMinimum(), y1),
                        QgsPointXY(bbox.xMinimum(), y0),
                    ]
                else:
                    span = bbox.width() / n
                    x0 = bbox.xMinimum() + i * span
                    x1 = bbox.xMinimum() + (i + 1) * span
                    pts = [
                        QgsPointXY(x0, bbox.yMinimum()),
                        QgsPointXY(x1, bbox.yMinimum()),
                        QgsPointXY(x1, bbox.yMaximum()),
                        QgsPointXY(x0, bbox.yMaximum()),
                        QgsPointXY(x0, bbox.yMinimum()),
                    ]
                strip_geom = QgsGeometry.fromPolygonXY([pts])
                intersected = ea_item['geom'].intersection(strip_geom)
                if not intersected.isEmpty():
                    strips.extend(get_polygons_from_geom(intersected))
            return strips

        use_horizontal = bbox.height() >= bbox.width()
        k_start = max(2, math.ceil(hh_cnt / float(target_pop)))
        k_max = k_start + 4

        accepted_parts = None
        accepted_k = None
        accepted_orientation = use_horizontal

        for k_val in range(k_start, k_max + 1):
            strip_polys = make_strips(k_val, horizontal=use_horizontal)
            orientation = 'horizontal'
            if len(strip_polys) < 2:
                strip_polys = make_strips(k_val, horizontal=not use_horizontal)
                orientation = 'vertical'

            if len(strip_polys) < 2:
                break

            parts = []
            for poly in strip_polys:
                buildings_in_poly = []
                for b in bldgs:
                    pt_geom = QgsGeometry.fromPointXY(b['point'])
                    if poly.contains(pt_geom) or poly.intersects(pt_geom):
                        buildings_in_poly.append(b)
                sub_pop = sum(b['pop'] for b in buildings_in_poly)
                parts.append({
                    'geom': poly,
                    'buildings': buildings_in_poly,
                    'hh_count': sub_pop,
                    'original_hhcount': ea_item.get('original_hhcount', 0),
                    'bldg_count': len(buildings_in_poly),
                    'bldgpoints_value': sub_pop / len(buildings_in_poly) if len(buildings_in_poly) > 0 else 0.0,
                    'attributes': list(ea_item['attributes']),
                    'original_id': ea_item['original_id'],
                    'original_code': ea_item['original_code'],
                    'is_new': True,
                    'from_split': True,
                    'split_by': 'forced_grid',
                    'parent_barangay': ea_item['parent_barangay']
                })

            is_parent_delin = is_parent_delineation_candidate(ea_item)
            if is_parent_delin:
                nonzero_parts = list(parts)
                zero_parts = []
            else:
                zero_parts = [p for p in parts if p['hh_count'] == 0]
                nonzero_parts = [p for p in parts if p['hh_count'] > 0]

            if not nonzero_parts:
                continue

            for zp in zero_parts:
                zp_centroid = zp['geom'].centroid().asPoint()
                best_nb = min(
                    nonzero_parts,
                    key=lambda np: zp_centroid.distance(np['geom'].centroid().asPoint())
                )
                raw_combined = best_nb['geom'].combine(zp['geom']).buffer(0.0, 3)
                clipped = raw_combined.intersection(ea_item['geom'])
                best_nb['geom'] = clipped if not clipped.isEmpty() else raw_combined
                best_nb['buildings'].extend(zp['buildings'])
                best_nb['bldg_count'] = len(best_nb['buildings'])

            parts = enforce_min_household(nonzero_parts, fback, ea_geom=ea_item['geom'])

            if len(parts) < 2:
                continue

            all_valid = all(p['hh_count'] <= max_household for p in parts)

            if accepted_parts is None or all_valid:
                accepted_parts = parts
                accepted_k = k_val
                accepted_orientation = orientation

            if all_valid:
                break

        if accepted_parts is None:
            fback.pushWarning(
                f"[EA {ea_item['original_code']}] FORCED SPLIT: Could not produce >= 2 valid "
                f"parts at any k ({k_start}–{k_max}). EA will remain over threshold."
            )
            return [ea_item]

        final_parts = []
        for part in accepted_parts:
            if part['hh_count'] > max_household:
                if part.get('from_merge', False):
                    final_parts.append(part)
                    continue
                sub_result = force_geometric_split(part, target_pop, fback)
                if len(sub_result) > 1:
                    final_parts.extend(sub_result)
                else:
                    final_parts.append(part)
            else:
                final_parts.append(part)

        orig_code_str = str(ea_item['original_code']).strip() if ea_item['original_code'] is not None else "000"
        digits = "".join([c for c in orig_code_str if c.isdigit()])
        orig_first3 = digits[:3] if len(digits) >= 3 else digits.zfill(3)
        if orig_first3 != "000" and len(final_parts) > 0:
            final_parts.sort(key=lambda x: x['hh_count'], reverse=True)
            final_parts[0]['is_new'] = False

        final_parts = allocate_gaps_to_parts(final_parts, ea_item['geom'])

        parent_geom = ea_item['geom']
        for p in final_parts:
            clipped = p['geom'].intersection(parent_geom).buffer(0.0, 3)
            if not clipped.isEmpty():
                p['geom'] = clipped

        fback.pushWarning(
            f"[EA {ea_item['original_code']}] FORCED SPLIT: Applied {accepted_orientation} "
            f"strip split (k={accepted_k}) — EA (hh_count={hh_cnt}) → {len(final_parts)} part(s)."
        )
        return final_parts

    def split_ea(ea_item, target_pop, fback):
        if fback.isCanceled():
            return [ea_item]
        bldgs = ea_item.get('buildings', [])
        if not bldgs:
            if is_delineation_candidate(ea_item):
                fback.pushInfo(f"[EA {ea_item['original_code']}] Delineation candidate has no building points. Forcing geometric split...")
                return force_geometric_split(ea_item, target_pop, fback)
            return [ea_item]
        road_lines = collect_linear_features(ea_item['geom'], road_index, road_geoms)
        river_lines = collect_linear_features(ea_item['geom'], river_index, river_geoms)
        all_lines = road_lines + river_lines
        line_geom = merge_line_geometries(all_lines)

        _ea_ean = str(ea_item.get('original_code', '')).strip()
        _ea_id = ea_item.get('original_id')
        hhdivthres = delineation_candidate_hhdivthres.get(_ea_id)
        if hhdivthres is None:
            hhdivthres = delineation_candidate_hhdivthres.get(_ea_ean)
        if hhdivthres is None:
            hhdivthres = max_household / ea_item['hh_count'] if ea_item['hh_count'] > 0.0 else 1.0

        unassigned_set = set(id(b) for b in bldgs)
        unassigned_list = [b for b in bldgs]
        unassigned_index = QgsSpatialIndex()
        bldg_id_map = {}
        for idx, b in enumerate(bldgs):
            feat = QgsFeature(idx)
            feat.setGeometry(QgsGeometry.fromPointXY(b['point']))
            unassigned_index.insertFeature(feat)
            bldg_id_map[idx] = b
            b['spatial_index_id'] = idx

        def remove_from_unassigned(bldg):
            unassigned_set.discard(id(bldg))
            feat = QgsFeature(bldg['spatial_index_id'])
            feat.setGeometry(QgsGeometry.fromPointXY(bldg['point']))
            unassigned_index.deleteFeature(feat)

        groups = []
        unassigned_idx_ptr = 0

        while unassigned_idx_ptr < len(unassigned_list):
            seed = unassigned_list[unassigned_idx_ptr]
            unassigned_idx_ptr += 1
            if id(seed) not in unassigned_set:
                continue

            remove_from_unassigned(seed)
            current_group = [seed]
            running_total = seed.get('bldgpoints_value', 0.0)

            group_frontier = [seed]

            while group_frontier:
                best_bldg = None
                best_group_pt = None
                min_dist = float('inf')

                stale_frontier = []
                for g_bldg in group_frontier:
                    g_pt = QgsPointXY(g_bldg['point'].x(), g_bldg['point'].y())
                    nearest_ids = unassigned_index.nearestNeighbor(g_pt, 1)
                    if nearest_ids:
                        n_id = nearest_ids[0]
                        n_b = bldg_id_map[n_id]
                        n_pt = QgsPointXY(n_b['point'].x(), n_b['point'].y())
                        dist = g_pt.distance(n_pt)
                        if dist < min_dist:
                            min_dist = dist
                            best_bldg = n_b
                            best_group_pt = g_pt
                    else:
                        stale_frontier.append(g_bldg)

                for sb in stale_frontier:
                    group_frontier.remove(sb)

                if best_bldg is None:
                    break

                is_separated = False
                if line_geom and not line_geom.isEmpty():
                    b_pt = QgsPointXY(best_bldg['point'].x(), best_bldg['point'].y())
                    segment_geom = QgsGeometry.fromPolylineXY([best_group_pt, b_pt])
                    if segment_geom.intersects(line_geom):
                        is_separated = True

                if is_separated:
                    break

                next_val = best_bldg.get('bldgpoints_value', 0.0)
                if running_total + next_val >= hhdivthres:
                    break

                current_group.append(best_bldg)
                group_frontier.append(best_bldg)
                remove_from_unassigned(best_bldg)
                running_total += next_val

            groups.append(current_group)

        pt_to_coords = {}
        for b in bldgs:
            pt_to_coords[(b['point'].x(), b['point'].y())] = b['point']
        unique_pts = list(pt_to_coords.values())

        point_based_parts = []
        if len(groups) >= 2 and len(unique_pts) >= 2:
            centroid_pts = [QgsPointXY(pt.x(), pt.y()) for pt in unique_pts]
            points_geom = QgsGeometry.fromMultiPointXY(centroid_pts)

            bbox = ea_item['geom'].boundingBox()
            buffer_size = max(0.01, max(bbox.width(), bbox.height()) * 0.2)
            extent_geom = QgsGeometry.fromRect(bbox.buffered(buffer_size))

            voronoi_geom = points_geom.voronoiDiagram(extent_geom)
            if not voronoi_geom.isEmpty():
                cells = get_polygons_from_geom(voronoi_geom)
                if cells:
                    if all_lines:
                        from qgis.analysis import QgsGeometrySnapper
                        line_index = QgsSpatialIndex()
                        line_map = {}
                        for l_idx, line in enumerate(all_lines):
                            feat = QgsFeature(l_idx)
                            feat.setGeometry(line)
                            line_index.insertFeature(feat)
                            line_map[l_idx] = line

                        snapped_cells = []
                        for cell_geom in cells:
                            buffered_bbox = cell_geom.boundingBox().buffered(snap_tolerance)
                            candidate_line_ids = line_index.intersects(buffered_bbox)

                            if not candidate_line_ids:
                                snapped_cells.append(cell_geom)
                                continue

                            nearby_lines = [line_map[lid] for lid in candidate_line_ids]

                            densified_cell = cell_geom.densifyByDistance(densify_dist)
                            snapped_cell = QgsGeometrySnapper.snapGeometry(
                                densified_cell,
                                snap_tolerance,
                                nearby_lines,
                                QgsGeometrySnapper.PreferClosest
                            )
                            clean_snapped_cell = snapped_cell.buffer(0.0, 3)
                            if clean_snapped_cell and not clean_snapped_cell.isEmpty():
                                snapped_cells.append(clean_snapped_cell)
                            else:
                                snapped_cells.append(cell_geom)
                        cells = snapped_cells

                    pt_to_cell = {}
                    for cell_geom in cells:
                        for pt in unique_pts:
                            pt_geom = QgsGeometry.fromPointXY(pt)
                            if cell_geom.contains(pt_geom) or cell_geom.intersects(pt_geom):
                                pt_to_cell[(pt.x(), pt.y())] = cell_geom

                    raw_parts = []
                    for g_idx, group in enumerate(groups):
                        group_cells = []
                        group_unique_coords = set()
                        for b in group:
                            coord = (b['point'].x(), b['point'].y())
                            if coord not in group_unique_coords:
                                group_unique_coords.add(coord)
                                cell = pt_to_cell.get(coord)
                                if cell:
                                    group_cells.append(cell)

                        if not group_cells:
                            continue

                        combined_geom = group_cells[0]
                        for cell in group_cells[1:]:
                            combined_geom = combined_geom.combine(cell)

                        combined_geom = combined_geom.buffer(0.0, 3)
                        intersected = ea_item['geom'].intersection(combined_geom)
                        if not intersected.isEmpty():
                            polys = get_polygons_from_geom(intersected)
                            for poly in polys:
                                buildings_in_poly = []
                                for b in group:
                                    pt_geom = QgsGeometry.fromPointXY(b['point'])
                                    if poly.contains(pt_geom) or poly.intersects(pt_geom):
                                        buildings_in_poly.append(b)

                                sub_pop = sum(b['pop'] for b in buildings_in_poly)
                                split_by = 'point_based'
                                if road_lines:
                                    split_by = 'road'
                                if river_lines:
                                    split_by = 'river' if split_by == 'road' else split_by + '+river'

                                raw_parts.append({
                                    'geom': poly,
                                    'buildings': buildings_in_poly,
                                    'hh_count': sub_pop,
                                    'original_hhcount': ea_item.get('original_hhcount', 0),
                                    'bldg_count': len(buildings_in_poly),
                                    'bldgpoints_value': sub_pop / len(buildings_in_poly) if len(buildings_in_poly) > 0 else 0.0,
                                    'attributes': list(ea_item['attributes']),
                                    'original_id': ea_item['original_id'],
                                    'original_code': ea_item['original_code'],
                                    'is_new': True,
                                    'from_split': True,
                                    'split_by': split_by,
                                    'parent_barangay': ea_item['parent_barangay']
                                })

                    if len(raw_parts) >= 2:
                        point_based_parts = enforce_min_household(raw_parts, fback, ea_geom=ea_item['geom'])

        if len(point_based_parts) >= 2:
            fback.pushInfo(f"[EA {ea_item['original_code']}] Point-based sequential split accepted: {len(point_based_parts)} parts created.")

            orig_code_str = str(ea_item['original_code']).strip() if ea_item['original_code'] is not None else "000"
            digits = "".join([c for c in orig_code_str if c.isdigit()])
            orig_first3 = digits[:3] if len(digits) >= 3 else digits.zfill(3)
            if orig_first3 != "000":
                point_based_parts.sort(key=lambda x: x['hh_count'], reverse=True)
                point_based_parts[0]['is_new'] = False

            parent_geom = ea_item['geom']
            for p in point_based_parts:
                clipped = p['geom'].intersection(parent_geom).buffer(0.0, 3)
                if not clipped.isEmpty():
                    p['geom'] = clipped
            point_based_parts = allocate_gaps_to_parts(point_based_parts, parent_geom)
            return point_based_parts

        fback.pushInfo(f"[EA {ea_item['original_code']}] Point-based sequential split could not partition EA. Falling back to K-Means + Voronoi...")

        split_parts = split_ea_voronoi(ea_item, target_pop, fback, split_by='none')

        if len(split_parts) < 2:
            fback.pushInfo(f"[EA {ea_item['original_code']}] K-Means + Voronoi failed. Falling back to Forced Geometric split...")
            split_parts = force_geometric_split(ea_item, target_pop, fback)

        if len(split_parts) >= 2:
            split_parts = enforce_bldgpv_threshold(split_parts, hhdivthres, fback, ea_geom=ea_item['geom'])

        parent_geom = ea_item['geom']
        for p in split_parts:
            clipped = p['geom'].intersection(parent_geom).buffer(0.0, 3)
            if not clipped.isEmpty():
                p['geom'] = clipped

        return split_parts

    def process_barangay_split(bar_code, bar_eas, fback):
        iteration = 0
        max_iterations = 5
        changed = True

        while changed and iteration < max_iterations:
            if fback.isCanceled():
                break

            has_overs = False
            for ea in bar_eas:
                if is_delineation_candidate(ea):
                    has_overs = True
                    break

            if not has_overs:
                break

            overs = []
            for idx, ea in enumerate(bar_eas):
                if is_delineation_candidate(ea):
                    overs.append(idx)

            changed = False

            if overs:
                new_eas = []
                for idx in range(len(bar_eas)):
                    if idx in overs:
                        ea = bar_eas[idx]
                        if ea.get('from_merge', False):
                            new_eas.append(ea)
                        else:
                            split_parts = split_ea(ea, max_household, fback)
                            if len(split_parts) > 1:
                                _ea_id = ea.get('original_id')
                                _ea_ean = str(ea.get('original_code', '')).strip()
                                _parent_hhdivthres = delineation_candidate_hhdivthres.get(_ea_id)
                                if _parent_hhdivthres is None:
                                    _parent_hhdivthres = delineation_candidate_hhdivthres.get(_ea_ean)
                                if _parent_hhdivthres is not None:
                                    _max_bldgpv = max(
                                        sum(b.get('bldgpoints_value', 0.0) for b in p['buildings'])
                                        for p in split_parts
                                    )
                                    if _max_bldgpv >= _parent_hhdivthres:
                                        fback.pushWarning(
                                            f"[Barangay {bar_code}] [EA {ea['original_code']}] "
                                            f"bldgpoints_value validation: max part's bldgpoints_value ({_max_bldgpv:.4f}) "
                                            f">= hhdivthres ({_parent_hhdivthres:.4f}). "
                                            f"Enforcing {min_household + 1}–{max_household - 1} HH range on parts."
                                        )
                                        split_parts = enforce_min_household(split_parts, fback, ea_geom=ea['geom'])
                                        split_parts = enforce_bldgpv_threshold(split_parts, _parent_hhdivthres, fback, ea_geom=ea['geom'])
                                new_eas.extend(split_parts)
                                changed = True
                                fback.pushInfo(f"[Barangay {bar_code}] Split over-populated EA (code={ea['original_code']}, pop={ea['hh_count']}) into {len(split_parts)} sub-polygons.")
                            else:
                                new_eas.append(ea)
                    else:
                        new_eas.append(bar_eas[idx])
                bar_eas = new_eas
                if changed:
                    iteration += 1
                    continue

        remaining_overs = [ea for ea in bar_eas if is_delineation_candidate(ea)]
        for ea in remaining_overs:
            unique_pt_count = len(set((b['point'].x(), b['point'].y()) for b in ea.get('buildings', [])))
            reason = []
            if unique_pt_count < 2:
                reason.append(f"only {unique_pt_count} unique building point(s) — Voronoi cannot split")
            if unique_pt_count >= 2:
                k_needed = max(2, int(round(ea['hh_count'] / float(target_household))))
                if k_needed > unique_pt_count:
                    reason.append(f"k={k_needed} required but only {unique_pt_count} unique points available")
            if not reason:
                reason.append("splitting consistently returned 1 part — check sliver threshold vs cell size")
            fback.pushWarning(
                f"[Barangay {bar_code}] UNRESOLVED OVER-THRESHOLD: EA (code={ea['original_code']}, "
                f"hh_count={ea['hh_count']}, bldg_count={ea.get('bldg_count',0)}, "
                f"unique_pts={unique_pt_count}) after {iteration} iteration(s). "
                f"Reason: {'; '.join(reason)}."
            )

        return bar_eas

    feedback.pushInfo("Running normal delineation...")

    barangay_groups = {}
    for ea in eas:
        bar = ea['parent_barangay']
        barangay_groups.setdefault(bar, []).append(ea)

    sorted_bar_keys = sorted(
        barangay_groups.keys(),
        key=lambda k: str(k) if k is not None else ""
    )

    split_bar_keys = [
        bar_code for bar_code in sorted_bar_keys
        if any(is_delineation_candidate(ea) for ea in barangay_groups[bar_code])
    ]

    multi_feedback.setCurrentStep(4)
    multi_feedback.setProgressText(
        f"{_PHASE_LABELS[4]} [0/{len(split_bar_keys)} barangay(s)]..."
    )

    def process_barangay_split_wrapper(bar_code, bar_eas, parent_feedback):
        result = process_barangay_split(bar_code, bar_eas, parent_feedback)
        return result, []

    split_eas = []

    if split_bar_keys:
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_cores) as executor:
            futures = {
                executor.submit(process_barangay_split_wrapper, bar_code, barangay_groups[bar_code], feedback): bar_code 
                for bar_code in split_bar_keys
            }

            _last_n_done = -1
            while not all(f.done() for f in futures.keys()):
                if multi_feedback.isCanceled():
                    for f in futures.keys():
                        f.cancel()
                    raise QgsProcessingException("Algorithm cancelled by user.")
                time.sleep(0.02)
                if QThread.currentThread() == QCoreApplication.instance().thread():
                    QCoreApplication.processEvents()

                _n_done = sum(1 for f in futures.keys() if f.done())
                if _n_done != _last_n_done:
                    _pct = int(_n_done / len(futures) * 100) if futures else 0
                    multi_feedback.setProgress(_pct)
                    multi_feedback.setProgressText(
                        f"{_PHASE_LABELS[4]} [{_n_done}/{len(futures)} barangay(s) done]..."
                    )
                    _last_n_done = _n_done

            ordered_futures = {bar_code: future for future, bar_code in futures.items()}
            for bar_code in sorted_bar_keys:
                if bar_code in ordered_futures:
                    future = ordered_futures[bar_code]
                    if future.cancelled():
                        split_eas.extend(barangay_groups[bar_code])
                        continue
                    try:
                        result, logs = future.result()
                        split_eas.extend(result)
                        for log_type, msg in logs:
                            if log_type == 'info':
                                feedback.pushInfo(msg)
                            elif log_type == 'warning':
                                feedback.pushWarning(msg)
                    except Exception as e:
                        feedback.reportError(f"Error splitting Barangay {bar_code}: {str(e)}")
                else:
                    split_eas.extend(barangay_groups[bar_code])
    else:
        for bar_code in sorted_bar_keys:
            split_eas.extend(barangay_groups[bar_code])

    multi_feedback.setProgress(100)

    if multi_feedback.isCanceled():
        raise QgsProcessingException("Algorithm cancelled by user.")

    return {
        "split_eas": split_eas
    }
