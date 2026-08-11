import math
from typing import Any, Dict, List, Set
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingException,
    QgsSpatialIndex,
    QgsFeature,
    QgsGeometry,
    QgsCoordinateTransform,
)
from PyQt5.QtCore import QVariant

from ..helpers.constants import yield_to_ui
from ..helpers.spatial import resolve_ea_parent_barangay


def run_phase_1(
    alg: QgsProcessingAlgorithm,
    parameters: Dict[str, Any],
    context: QgsProcessingContext,
    feedback: QgsProcessingFeedback,
) -> Dict[str, Any]:
    """Phase 1/8: Initializing — reading parameters, loading layers, processing Gap/Overlap, calculating sliver threshold."""
    # Retrieve input parameters
    barangay_source = alg.parameterAsSource(parameters, alg.BARANGAY_INPUT, context)
    if barangay_source is None:
        raise QgsProcessingException(alg.invalidSourceError(parameters, alg.BARANGAY_INPUT))

    building_source = alg.parameterAsSource(parameters, alg.BUILDING_INPUT, context)
    if building_source is None:
        raise QgsProcessingException(alg.invalidSourceError(parameters, alg.BUILDING_INPUT))

    previous_ea_source = alg.parameterAsSource(parameters, alg.PREVIOUS_EA_INPUT, context)
    if previous_ea_source is None:
        raise QgsProcessingException(alg.invalidSourceError(parameters, alg.PREVIOUS_EA_INPUT))

    road_source = alg.parameterAsSource(parameters, alg.ROAD_INPUT, context)
    river_source = alg.parameterAsSource(parameters, alg.RIVER_INPUT, context)
    gap_source = alg.parameterAsSource(parameters, alg.GAP_INPUT, context)
    overlap_source = alg.parameterAsSource(parameters, alg.OVERLAP_INPUT, context)
    snap_tolerance_m = alg.parameterAsDouble(parameters, alg.SNAP_TOLERANCE, context)
    preview_only = alg.parameterAsBoolean(parameters, alg.PREVIEW_ONLY, context)
    allow_candidate_merge = alg.parameterAsBoolean(parameters, getattr(alg, 'ALLOW_CANDIDATE_MERGE', 'ALLOW_CANDIDATE_MERGE'), context)

    # Resolve dynamic field names from Previous EA Layer case-insensitively
    ea_fields = previous_ea_source.fields()
    eadel_indi_col_idx = -1
    merge_indi_col_idx = -1
    for i in range(ea_fields.count()):
        name_lower = ea_fields.at(i).name().lower()
        if name_lower == "eadel_indi":
            eadel_indi_col_idx = i
        elif name_lower == "merge_indi":
            merge_indi_col_idx = i

    ea_id_field = "ean"
    for i in range(ea_fields.count()):
        name_lower = ea_fields.at(i).name().lower()
        if name_lower in ["ean", "ea_number", "ea_code", "id"]:
            ea_id_field = ea_fields.at(i).name()
            break

    household_field = "hhcount"
    for i in range(ea_fields.count()):
        name_lower = ea_fields.at(i).name().lower()
        if name_lower in ["hhcount", "hh_count", "household", "household_count"]:
            household_field = ea_fields.at(i).name()
            break

    bldg_fields = building_source.fields()
    bldg_hh_field = "hhcount"
    for i in range(bldg_fields.count()):
        if bldg_fields.at(i).name().lower() == "hhcount":
            bldg_hh_field = bldg_fields.at(i).name()
            break

    barangay_id_field = "geocode"
    for i in range(ea_fields.count()):
        name_lower = ea_fields.at(i).name().lower()
        if name_lower in ["geocode", "bgy_geocode", "brgy_geocode", "barangay_code"]:
            barangay_id_field = ea_fields.at(i).name()
            break

    bar_fields = barangay_source.fields()
    bar_geocode_field = "geocode"
    for i in range(bar_fields.count()):
        name_lower = bar_fields.at(i).name().lower()
        if name_lower in ["geocode", "bgy_geocode", "brgy_geocode", "barangay_code"]:
            bar_geocode_field = bar_fields.at(i).name()
            break

    min_household = alg.parameterAsInt(parameters, alg.MIN_HOUSEHOLD, context)
    max_household = alg.parameterAsInt(parameters, alg.MAX_HOUSEHOLD, context)
    target_household = int((min_household + max_household) / 2)
    target_crs = alg.parameterAsCrs(parameters, alg.TARGET_CRS, context)

    feedback.pushInfo("Building spatial index of Barangay Layer...")
    barangay_index = QgsSpatialIndex()
    barangay_by_id = {}
    active_barangay_geocodes = set()

    bar_geocode_idx = barangay_source.fields().indexOf(bar_geocode_field)

    for idx, feat in enumerate(barangay_source.getFeatures()):
        if feedback.isCanceled():
            raise QgsProcessingException("Algorithm cancelled by user.")
        yield_to_ui(idx)
        barangay_index.insertFeature(feat)
        barangay_by_id[feat.id()] = feat

        if bar_geocode_idx != -1:
            val = feat.attribute(bar_geocode_idx)
            if val is not None:
                val_str = str(val).strip()
                if val_str.endswith(".0"):
                    val_str = val_str[:-2]
                if val_str:
                    if len(val_str) > 9:
                        val_str = val_str[:9]
                    active_barangay_geocodes.add(val_str)

    _dc_geo_idx = previous_ea_source.fields().indexOf(barangay_id_field)
    if _dc_geo_idx == -1:
        _dc_geo_idx = previous_ea_source.fields().indexOf("geocode")

    feedback.pushInfo("Caching relevant previous EA features in memory...")
    all_ea_features = []
    _ea_load_cnt = 0
    for feat in previous_ea_source.getFeatures():
        if feedback.isCanceled():
            raise QgsProcessingException("Algorithm cancelled by user.")

        geom = feat.geometry()
        if geom and not geom.isEmpty():
            parent_bar = resolve_ea_parent_barangay(
                feat, _dc_geo_idx, barangay_id_field, barangay_index, barangay_by_id
            )
            parent_bar_sub = parent_bar[:9] if len(parent_bar) >= 9 else parent_bar
            if parent_bar and parent_bar != "Unknown" and (
                parent_bar in active_barangay_geocodes or parent_bar_sub in active_barangay_geocodes
            ):
                all_ea_features.append(feat)
        _ea_load_cnt += 1
        yield_to_ui(_ea_load_cnt, 1000)

    # Gap and Overlap workflow
    special_ea_info = {}
    special_ea_ids = set()

    if gap_source is not None or overlap_source is not None:
        gaps_count = 0
        overlaps_count = 0
        special_ea_counter = 0

        max_fid = max([feat.id() for feat in all_ea_features]) if all_ea_features else 0
        special_ea_features = []

        if gap_source is not None:
            feedback.pushInfo("Gap layer detected.")
            feedback.pushInfo("Scanning affected EAs...")

            gap_to_ea_transform = None
            if gap_source.sourceCrs() != previous_ea_source.sourceCrs():
                gap_to_ea_transform = QgsCoordinateTransform(
                    gap_source.sourceCrs(), previous_ea_source.sourceCrs(), context.transformContext()
                )

            for go_feat in gap_source.getFeatures():
                if feedback.isCanceled():
                    raise QgsProcessingException("Algorithm cancelled by user.")

                go_geom = go_feat.geometry()
                if not go_geom or go_geom.isEmpty():
                    continue

                go_geom = QgsGeometry(go_geom)
                if gap_to_ea_transform:
                    go_geom.transform(gap_to_ea_transform)
                go_geom = go_geom.makeValid()

                candidates = barangay_index.intersects(go_geom.boundingBox())
                best_bar_feat = None
                max_bar_overlap = -1
                for cid in candidates:
                    bar_feat = barangay_by_id[cid]
                    bar_geom = bar_feat.geometry()
                    if bar_geom.intersects(go_geom):
                        overlap_area = bar_geom.intersection(go_geom).area()
                        if overlap_area > max_bar_overlap:
                            max_bar_overlap = overlap_area
                            best_bar_feat = bar_feat

                if best_bar_feat is None:
                    continue

                go_geom = go_geom.intersection(best_bar_feat.geometry()).makeValid()
                if go_geom.isEmpty():
                    continue

                parent_bar_geo = str(best_bar_feat.attribute(bar_geocode_field)).strip()
                if parent_bar_geo.endswith(".0"):
                    parent_bar_geo = parent_bar_geo[:-2]

                special_type = "GAP"
                gaps_count += 1

                intersecting_eas = []
                max_ea_overlap = -1
                primary_ea_feat = None

                for ea_feat in all_ea_features:
                    if ea_feat.geometry().intersects(go_geom):
                        overlap_area = ea_feat.geometry().intersection(go_geom).area()
                        if overlap_area > 1e-9:
                            intersecting_eas.append((ea_feat, overlap_area))
                            if overlap_area > max_ea_overlap:
                                max_ea_overlap = overlap_area
                                primary_ea_feat = ea_feat

                for ea_feat, _ in intersecting_eas:
                    new_geom = ea_feat.geometry().difference(go_geom).makeValid()
                    ea_feat.setGeometry(new_geom)

                special_ea_feat = QgsFeature(previous_ea_source.fields())
                special_ea_feat.setGeometry(go_geom)

                special_ea_attrs = None
                if primary_ea_feat:
                    special_ea_attrs = list(primary_ea_feat.attributes())
                else:
                    fallback_ea_feat = None
                    for ea_feat in all_ea_features:
                        if resolve_ea_parent_barangay(
                            ea_feat, _dc_geo_idx, barangay_id_field, barangay_index, barangay_by_id
                        ) == parent_bar_geo:
                            fallback_ea_feat = ea_feat
                            break
                    if fallback_ea_feat:
                        special_ea_attrs = list(fallback_ea_feat.attributes())
                    else:
                        special_ea_attrs = [None] * previous_ea_source.fields().count()

                geocode_field_idx = previous_ea_source.fields().indexOf(barangay_id_field)
                if geocode_field_idx != -1 and geocode_field_idx < len(special_ea_attrs):
                    special_ea_attrs[geocode_field_idx] = parent_bar_geo

                special_ea_feat.setAttributes(special_ea_attrs)

                special_ea_counter += 1
                new_fid = max_fid + special_ea_counter
                special_ea_feat.setId(new_fid)

                go_source_id = str(go_feat.attribute("id")) if go_feat.fields().indexOf("id") != -1 and go_feat.attribute("id") is not None else str(go_feat.id())
                special_ea_info[new_fid] = {
                    'special_type': special_type,
                    'source_id': go_source_id,
                    'remarks': 'Generated from Gap layer',
                    'original_code': str(primary_ea_feat.attribute(ea_id_field)) if primary_ea_feat else (str(fallback_ea_feat.attribute(ea_id_field)) if fallback_ea_feat else "000")
                }
                special_ea_ids.add(new_fid)
                special_ea_features.append(special_ea_feat)

        if overlap_source is not None:
            feedback.pushInfo("Overlap layer detected.")
            feedback.pushInfo("Scanning affected EAs...")

            overlap_to_ea_transform = None
            if overlap_source.sourceCrs() != previous_ea_source.sourceCrs():
                overlap_to_ea_transform = QgsCoordinateTransform(
                    overlap_source.sourceCrs(), previous_ea_source.sourceCrs(), context.transformContext()
                )

            for go_feat in overlap_source.getFeatures():
                if feedback.isCanceled():
                    raise QgsProcessingException("Algorithm cancelled by user.")

                go_geom = go_feat.geometry()
                if not go_geom or go_geom.isEmpty():
                    continue

                go_geom = QgsGeometry(go_geom)
                if overlap_to_ea_transform:
                    go_geom.transform(overlap_to_ea_transform)
                go_geom = go_geom.makeValid()

                candidates = barangay_index.intersects(go_geom.boundingBox())
                best_bar_feat = None
                max_bar_overlap = -1
                for cid in candidates:
                    bar_feat = barangay_by_id[cid]
                    bar_geom = bar_feat.geometry()
                    if bar_geom.intersects(go_geom):
                        overlap_area = bar_geom.intersection(go_geom).area()
                        if overlap_area > max_bar_overlap:
                            max_bar_overlap = overlap_area
                            best_bar_feat = bar_feat

                if best_bar_feat is None:
                    continue

                go_geom = go_geom.intersection(best_bar_feat.geometry()).makeValid()
                if go_geom.isEmpty():
                    continue

                parent_bar_geo = str(best_bar_feat.attribute(bar_geocode_field)).strip()
                if parent_bar_geo.endswith(".0"):
                    parent_bar_geo = parent_bar_geo[:-2]

                special_type = "OVERLAP"
                overlaps_count += 1

                intersecting_eas = []
                max_ea_overlap = -1
                primary_ea_feat = None

                for ea_feat in all_ea_features:
                    if ea_feat.geometry().intersects(go_geom):
                        overlap_area = ea_feat.geometry().intersection(go_geom).area()
                        if overlap_area > 1e-9:
                            intersecting_eas.append((ea_feat, overlap_area))
                            if overlap_area > max_ea_overlap:
                                max_ea_overlap = overlap_area
                                primary_ea_feat = ea_feat

                for ea_feat, _ in intersecting_eas:
                    new_geom = ea_feat.geometry().difference(go_geom).makeValid()
                    ea_feat.setGeometry(new_geom)

                special_ea_feat = QgsFeature(previous_ea_source.fields())
                special_ea_feat.setGeometry(go_geom)

                special_ea_attrs = None
                if primary_ea_feat:
                    special_ea_attrs = list(primary_ea_feat.attributes())
                else:
                    fallback_ea_feat = None
                    for ea_feat in all_ea_features:
                        if resolve_ea_parent_barangay(
                            ea_feat, _dc_geo_idx, barangay_id_field, barangay_index, barangay_by_id
                        ) == parent_bar_geo:
                            fallback_ea_feat = ea_feat
                            break
                    if fallback_ea_feat:
                        special_ea_attrs = list(fallback_ea_feat.attributes())
                    else:
                        special_ea_attrs = [None] * previous_ea_source.fields().count()

                geocode_field_idx = previous_ea_source.fields().indexOf(barangay_id_field)
                if geocode_field_idx != -1 and geocode_field_idx < len(special_ea_attrs):
                    special_ea_attrs[geocode_field_idx] = parent_bar_geo

                special_ea_feat.setAttributes(special_ea_attrs)

                special_ea_counter += 1
                new_fid = max_fid + special_ea_counter
                special_ea_feat.setId(new_fid)

                go_source_id = str(go_feat.attribute("id")) if go_feat.fields().indexOf("id") != -1 and go_feat.attribute("id") is not None else str(go_feat.id())
                special_ea_info[new_fid] = {
                    'special_type': special_type,
                    'source_id': go_source_id,
                    'remarks': 'Generated from Overlap layer',
                    'original_code': str(primary_ea_feat.attribute(ea_id_field)) if primary_ea_feat else (str(fallback_ea_feat.attribute(ea_id_field)) if fallback_ea_feat else "000")
                }
                special_ea_ids.add(new_fid)
                special_ea_features.append(special_ea_feat)

        if gap_source is not None:
            feedback.pushInfo(f"{gaps_count} Gap polygons processed.")
        if overlap_source is not None:
            feedback.pushInfo(f"{overlaps_count} Overlap polygons processed.")
        feedback.pushInfo(f"Creating {special_ea_counter} Special EAs...")

        all_ea_features.extend(special_ea_features)

    # Extract 5-digit geocode prefix
    geocode_prefix = ""
    try:
        for feat in barangay_source.getFeatures():
            val = feat.attribute(barangay_id_field)
            if val is not None:
                val_str = str(val).strip()
                if val_str.endswith(".0"):
                    val_str = val_str[:-2]
                digits = "".join([c for c in val_str if c.isdigit()])
                if len(digits) >= 5:
                    geocode_prefix = digits[:5]
                    break
                elif len(digits) > 0 and not geocode_prefix:
                    geocode_prefix = digits
    except Exception as e:
        feedback.pushInfo(f"Error extracting geocode prefix from Barangay layer: {str(e)}")

    if not geocode_prefix:
        try:
            ea_geocode_field = "geocode"
            if previous_ea_source.fields().indexOf(ea_geocode_field) != -1:
                for feat in all_ea_features:
                    val = feat.attribute(ea_geocode_field)
                    if val is not None:
                        val_str = str(val).strip()
                        if val_str.endswith(".0"):
                            val_str = val_str[:-2]
                        digits = "".join([c for c in val_str if c.isdigit()])
                        if len(digits) >= 5:
                            geocode_prefix = digits[:5]
                            break
        except Exception as e:
            feedback.pushInfo(f"Error extracting geocode prefix from Previous EA layer: {str(e)}")

    if not geocode_prefix:
        geocode_prefix = "00000"

    output_layer_name = f"{geocode_prefix}_ea2026"
    feedback.pushInfo(f"Calculated output layer name: {output_layer_name}")

    source_crs = previous_ea_source.sourceCrs()
    if source_crs.isGeographic():
        snap_tolerance = snap_tolerance_m / 111320.0
        densify_dist = 10.0 / 111320.0
    else:
        snap_tolerance = snap_tolerance_m
        densify_dist = 10.0

    building_crs = building_source.sourceCrs()
    transform = None
    if source_crs != building_crs:
        feedback.pushInfo(f"Transforming buildings from {building_crs.authid()} to {source_crs.authid()}...")
        transform = QgsCoordinateTransform(building_crs, source_crs, context.transformContext())

    sliver_threshold_idx = alg.parameterAsInt(parameters, alg.SLIVER_THRESHOLD, context)
    is_geo = source_crs.isGeographic()
    if sliver_threshold_idx == 0:
        feedback.pushInfo("Calculating sliver threshold based on clustering/spacing of building points...")
        sample_pts = []
        bldg_count = building_source.featureCount()
        if bldg_count > 0:
            sample_step = max(1, bldg_count // 1000)
            cnt = 0
            for feat in building_source.getFeatures():
                if cnt % sample_step == 0:
                    geom = feat.geometry()
                    if geom and not geom.isEmpty():
                        if transform:
                            geom_clone = QgsGeometry(geom)
                            geom_clone.transform(transform)
                            p = geom_clone.asPoint()
                        else:
                            p = geom.asPoint()
                        sample_pts.append(p)
                cnt += 1
                if len(sample_pts) >= 1000:
                    break

        if len(sample_pts) > 1:
            sample_index = QgsSpatialIndex()
            pt_geoms = {}
            for idx, pt in enumerate(sample_pts):
                f = QgsFeature(idx)
                f.setGeometry(QgsGeometry.fromPointXY(pt))
                sample_index.insertFeature(f)
                pt_geoms[idx] = pt

            distances = []
            for idx, pt in enumerate(sample_pts):
                neighbors = sample_index.nearestNeighbor(pt, 2)
                for n_id in neighbors:
                    if n_id != idx:
                        n_pt = pt_geoms[n_id]
                        dist = pt.distance(n_pt)
                        if dist > 0:
                            distances.append(dist)
                        break

            if distances:
                avg_nn_dist = sum(distances) / len(distances)
                auto_threshold = 0.01 * (avg_nn_dist ** 2)
                feedback.pushInfo(f"Average nearest neighbor building spacing: {avg_nn_dist:.6f}. Calculated raw threshold: {auto_threshold:.12f}")
            else:
                auto_threshold = None
        else:
            auto_threshold = None

        if auto_threshold is not None:
            if is_geo:
                area_threshold = max(1e-13, min(auto_threshold, 1e-3))
            else:
                area_threshold = max(1e-6, min(auto_threshold, 10000.0))
        else:
            total_ea_area = 0.0
            valid_ea_count = 0
            for feat in all_ea_features:
                geom = feat.geometry()
                if geom and not geom.isEmpty():
                    total_ea_area += geom.area()
                    valid_ea_count += 1

            if valid_ea_count > 0:
                avg_ea_area = total_ea_area / valid_ea_count
                auto_threshold = avg_ea_area * 1e-7
                if is_geo:
                    area_threshold = max(1e-13, min(auto_threshold, 1e-9))
                else:
                    area_threshold = max(1e-6, min(auto_threshold, 1.0))
            else:
                area_threshold = 1e-11 if is_geo else 1e-4
    elif sliver_threshold_idx == 1:
        area_threshold = 1e-11 if is_geo else 1e-4
    elif sliver_threshold_idx == 2:
        area_threshold = 1e-9 if is_geo else 1e-2
    elif sliver_threshold_idx == 3:
        area_threshold = 1e-7 if is_geo else 1.0
    elif sliver_threshold_idx == 4:
        area_threshold = 1e-5 if is_geo else 100.0
    elif sliver_threshold_idx == 5:
        area_threshold = 1e-13 if is_geo else 1e-6
    elif sliver_threshold_idx == 6:
        area_threshold = 1e-4 if is_geo else 1000.0
    elif sliver_threshold_idx == 7:
        area_threshold = 1e-3 if is_geo else 10000.0
    else:
        area_threshold = 1e-11 if is_geo else 1e-4

    feedback.pushInfo(f"Using automatically chosen sliver polygon area threshold: {area_threshold}")
    feedback.pushInfo(f"Previous EA Source CRS: {source_crs.authid()}")
    feedback.pushInfo(f"Target CRS: {target_crs.authid()}")
    feedback.pushInfo(f"Household Threshold: {min_household} - {max_household} HH (Target: {target_household} HH)")
    feedback.pushInfo(f"Input Barangay Count: {barangay_source.featureCount()}")
    feedback.pushInfo(f"Input Previous EA Count: {previous_ea_source.featureCount()}")
    feedback.pushInfo(f"Input Building Count: {building_source.featureCount()}")

    split_strategy = alg.parameterAsEnum(parameters, getattr(alg, 'SPLIT_STRATEGY', 'SPLIT_STRATEGY'), context) if hasattr(alg, 'SPLIT_STRATEGY') else 0

    return {
        "barangay_source": barangay_source,
        "building_source": building_source,
        "previous_ea_source": previous_ea_source,
        "road_source": road_source,
        "river_source": river_source,
        "gap_source": gap_source,
        "overlap_source": overlap_source,
        "snap_tolerance_m": snap_tolerance_m,
        "preview_only": preview_only,
        "allow_candidate_merge": allow_candidate_merge,
        "split_strategy": split_strategy,
        "eadel_indi_col_idx": eadel_indi_col_idx,
        "merge_indi_col_idx": merge_indi_col_idx,
        "ea_id_field": ea_id_field,
        "household_field": household_field,
        "bldg_hh_field": bldg_hh_field,
        "barangay_id_field": barangay_id_field,
        "bar_geocode_field": bar_geocode_field,
        "min_household": min_household,
        "max_household": max_household,
        "target_household": target_household,
        "target_crs": target_crs,
        "barangay_index": barangay_index,
        "barangay_by_id": barangay_by_id,
        "active_barangay_geocodes": active_barangay_geocodes,
        "_dc_geo_idx": _dc_geo_idx,
        "all_ea_features": all_ea_features,
        "special_ea_info": special_ea_info,
        "special_ea_ids": special_ea_ids,
        "output_layer_name": output_layer_name,
        "snap_tolerance": snap_tolerance,
        "densify_dist": densify_dist,
        "transform": transform,
        "area_threshold": area_threshold,
        "source_crs": source_crs,
    }
