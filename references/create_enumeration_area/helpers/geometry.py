import math
import random
from typing import List, Dict, Any, Optional, Tuple

from qgis.core import (
    QgsGeometry,
    QgsWkbTypes,
    QgsSpatialIndex,
    QgsPointXY,
)


def get_polylines_from_geom(geom: QgsGeometry) -> List[List[QgsPointXY]]:
    """Helper to extract individual polylines (as list of QgsPointXY) from a QgsGeometry."""
    lines = []
    if geom.isEmpty():
        return lines
    flat_type = QgsWkbTypes.flatType(geom.wkbType())
    if flat_type == QgsWkbTypes.LineString:
        pts = geom.asPolyline()
        if pts and len(pts) >= 2:
            lines.append(pts)
    elif flat_type in (QgsWkbTypes.MultiLineString, QgsWkbTypes.GeometryCollection) or geom.isMultipart():
        try:
            for part in geom.constParts():
                part_pts = [QgsPointXY(pt.x(), pt.y()) for pt in part]
                if len(part_pts) >= 2:
                    lines.append(part_pts)
        except Exception:
            pts = geom.asPolyline()
            if pts and len(pts) >= 2:
                lines.append(pts)
    else:
        pts = geom.asPolyline()
        if pts and len(pts) >= 2:
            lines.append(pts)
    return lines


def get_polygons_from_geom(geom: QgsGeometry) -> List[QgsGeometry]:
    """Helper to extract individual contiguous polygon parts from a QgsGeometry."""
    polys = []
    if geom.isEmpty():
        return polys
    
    flat_type = QgsWkbTypes.flatType(geom.wkbType())
    
    if flat_type == QgsWkbTypes.Polygon:
        polys.append(geom)
    elif flat_type == QgsWkbTypes.MultiPolygon:
        for part in geom.constParts():
            polys.append(QgsGeometry(part.clone()))
    elif flat_type == QgsWkbTypes.GeometryCollection or geom.isMultipart():
        try:
            for part in geom.constParts():
                part_geom = QgsGeometry(part.clone())
                part_flat = QgsWkbTypes.flatType(part_geom.wkbType())
                if part_flat == QgsWkbTypes.Polygon:
                    polys.append(part_geom)
                elif part_flat == QgsWkbTypes.MultiPolygon:
                    for sub_part in part_geom.constParts():
                        polys.append(QgsGeometry(sub_part.clone()))
                elif part_flat == QgsWkbTypes.GeometryCollection:
                    polys.extend(get_polygons_from_geom(part_geom))
        except Exception:
            if flat_type in (QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon):
                polys.append(geom)
    else:
        if flat_type in (QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon):
            polys.append(geom)
        
    # Clean each polygon individually to prevent dissolving shared boundaries
    cleaned_polys = []
    for p in polys:
        cp = p.buffer(0.0, 3)
        if cp and not cp.isEmpty():
            cp_flat = QgsWkbTypes.flatType(cp.wkbType())
            if cp_flat in (QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon):
                cleaned_polys.append(cp)
            elif cp_flat == QgsWkbTypes.GeometryCollection or cp.isMultipart():
                for part in cp.constParts():
                    part_geom = QgsGeometry(part.clone())
                    part_flat = QgsWkbTypes.flatType(part_geom.wkbType())
                    if part_flat in (QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon):
                        cleaned_polys.append(part_geom)
        else:
            p_flat = QgsWkbTypes.flatType(p.wkbType())
            if p_flat in (QgsWkbTypes.Polygon, QgsWkbTypes.MultiPolygon):
                cleaned_polys.append(p)
    return cleaned_polys


def allocate_gaps_to_parts(parts: List[Dict[str, Any]], parent_geom: QgsGeometry) -> List[Dict[str, Any]]:
    """Allocate gaps/holes in the union of parts to their nearest parent part."""
    if not parts:
        return parts
    
    # Compute union of parts
    parts_union = parts[0]['geom']
    for p in parts[1:]:
        parts_union = parts_union.combine(p['geom'])
        
    # Get gaps
    gaps = parent_geom.difference(parts_union).buffer(0.0, 3)
    if gaps.isEmpty():
        return parts
        
    # Extract individual polygons from gaps
    gap_polys = get_polygons_from_geom(gaps)
    for gap_poly in gap_polys:
        if gap_poly.isEmpty():
            continue
        # Find the part that shares the longest boundary with this gap polygon
        best_part = None
        max_boundary_len = -1.0
        for p in parts:
            shared = gap_poly.intersection(p['geom'])
            if not shared.isEmpty():
                boundary_len = shared.length()
                if boundary_len > max_boundary_len:
                    max_boundary_len = boundary_len
                    best_part = p
                    
        # Fallback: assign to the nearest part by centroid distance
        if best_part is None:
            gap_centroid = gap_poly.centroid().asPoint()
            best_part = min(parts, key=lambda p: math.hypot(gap_centroid.x() - p['geom'].centroid().asPoint().x(), gap_centroid.y() - p['geom'].centroid().asPoint().y()))
            
        # Combine gap polygon with the selected part
        combined = best_part['geom'].combine(gap_poly).buffer(0.0, 3)
        best_part['geom'] = combined
    return parts


def collect_linear_features(
    ea_geom: QgsGeometry,
    index: Optional[QgsSpatialIndex],
    geoms_dict: Dict[int, QgsGeometry]
) -> List[QgsGeometry]:
    """Return road/river line geometries clipped strictly to the EA polygon boundary."""
    if index is None or not geoms_dict:
        return []
    candidates = index.intersects(ea_geom.boundingBox())
    lines = []
    for fid in candidates:
        geom = geoms_dict.get(fid)
        if geom and not geom.isEmpty() and ea_geom.intersects(geom):
            clipped = geom.intersection(ea_geom)
            if not clipped.isEmpty():
                flat_type = QgsWkbTypes.flatType(clipped.wkbType())
                if flat_type in (QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString):
                    lines.append(clipped)
                elif flat_type == QgsWkbTypes.GeometryCollection or clipped.isMultipart():
                    for part in clipped.constParts():
                        p_geom = QgsGeometry(part.clone())
                        p_flat = QgsWkbTypes.flatType(p_geom.wkbType())
                        if p_flat in (QgsWkbTypes.LineString, QgsWkbTypes.MultiLineString):
                            lines.append(p_geom)
    return lines


def merge_line_geometries(line_geoms: List[QgsGeometry]) -> Optional[QgsGeometry]:
    """Union a list of line geometries into a single geometry (or None)."""
    if not line_geoms:
        return None
    merged = line_geoms[0]
    for lg in line_geoms[1:]:
        merged = merged.combine(lg)
    return merged


def weighted_kmeans(
    points: List[Tuple[float, float]],
    weights: List[float],
    k_val: int,
    max_iters: int = 30
) -> Tuple[List[int], List[Tuple[float, float]]]:
    """Pure Python weighted K-Means clustering algorithm."""
    n_pts = len(points)
    if n_pts <= k_val:
        return list(range(n_pts)), list(points)
        
    random.seed(42)
    total_w = sum(weights)
    if total_w > 0:
        cx = sum(p[0] * w for p, w in zip(points, weights)) / total_w
        cy = sum(p[1] * w for p, w in zip(points, weights)) / total_w
        first_idx = min(range(n_pts),
                        key=lambda i: math.hypot(points[i][0] - cx, points[i][1] - cy))
        centroids = [points[first_idx]]
    else:
        centroids = [points[0]]

    for _ in range(1, k_val):
        sq_dists = []
        for pt in points:
            min_d = min(math.hypot(pt[0] - c[0], pt[1] - c[1]) for c in centroids)
            sq_dists.append(min_d * min_d)
        total_sq = sum(sq_dists)
        if total_sq == 0:
            chosen = points[0]
            for pt in points:
                if pt not in centroids:
                    chosen = pt
                    break
        else:
            r = random.random() * total_sq
            cumulative = 0.0
            chosen = points[-1]
            for pt, sq_d in zip(points, sq_dists):
                cumulative += sq_d
                if cumulative >= r:
                    chosen = pt
                    break
        centroids.append(chosen)

    labels = [0] * n_pts
    for iter_idx in range(max_iters):
        new_labels = []
        for pt in points:
            min_dist = float('inf')
            best_idx = 0
            for i, c in enumerate(centroids):
                d = math.hypot(pt[0] - c[0], pt[1] - c[1])
                if d < min_dist:
                    min_dist = d
                    best_idx = i
            new_labels.append(best_idx)
            
        if new_labels == labels and iter_idx > 0:
            break
        labels = new_labels
        
        sum_x = [0.0] * k_val
        sum_y = [0.0] * k_val
        sum_w = [0.0] * k_val
        for pt, w, l in zip(points, weights, labels):
            sum_x[l] += pt[0] * w
            sum_y[l] += pt[1] * w
            sum_w[l] += w
            
        centroids = []
        for i in range(k_val):
            if sum_w[i] > 0:
                centroids.append((sum_x[i] / sum_w[i], sum_y[i] / sum_w[i]))
            else:
                centroids.append(random.choice(points))
                
    return labels, centroids


def assign_buildings_to_parts(
    bldgs: List[Dict[str, Any]],
    part_geoms: List[QgsGeometry],
    fback: Any = None,
    parent_code: str = ""
) -> List[List[Dict[str, Any]]]:
    """
    Assign building points exclusively to sub-polygon geometries.
    
    Guarantees:
    1. Every building is assigned to EXACTLY ONE sub-polygon (zero HH lost, zero HH duplicated).
    2. Primary: Strict geometric containment (poly.contains).
    3. Tie-breaker (boundary points): Assigned to the polygon whose centroid is closest.
    4. Orphan recovery (points in geometric gaps/buffers): Assigned to the nearest polygon by centroid distance.
    """
    n_parts = len(part_geoms)
    if n_parts == 0:
        return []
    if n_parts == 1:
        return [list(bldgs)]

    # Pre-calculate centroids and bounding boxes for fast spatial matching
    centroids = []
    bboxes = []
    for g in part_geoms:
        if g and not g.isEmpty():
            c = g.centroid().asPoint()
            centroids.append(c)
            bboxes.append(g.boundingBox())
        else:
            centroids.append(QgsPointXY(0.0, 0.0))
            bboxes.append(None)

    assignments = [None] * len(bldgs)

    for b_idx, b in enumerate(bldgs):
        pt = b['point']
        pt_xy = pt if isinstance(pt, QgsPointXY) else QgsPointXY(pt[0], pt[1])
        pt_geom = QgsGeometry.fromPointXY(pt_xy)

        # 1. Check strict containment
        contained_parts = []
        for p_idx, poly in enumerate(part_geoms):
            if poly and not poly.isEmpty():
                if bboxes[p_idx] and not bboxes[p_idx].contains(pt_xy):
                    continue
                if poly.contains(pt_geom):
                    contained_parts.append(p_idx)

        if len(contained_parts) == 1:
            assignments[b_idx] = contained_parts[0]
        elif len(contained_parts) > 1:
            # Boundary case (shared edge / point in multiple parts) -> nearest centroid
            assignments[b_idx] = min(
                contained_parts,
                key=lambda pi: math.hypot(pt_xy.x() - centroids[pi].x(), pt_xy.y() - centroids[pi].y())
            )
        else:
            # 2. Not strictly contained -> check intersection (touching boundary)
            intersected_parts = []
            for p_idx, poly in enumerate(part_geoms):
                if poly and not poly.isEmpty():
                    if bboxes[p_idx] and not bboxes[p_idx].contains(pt_xy):
                        continue
                    if poly.intersects(pt_geom):
                        intersected_parts.append(p_idx)

            if len(intersected_parts) == 1:
                assignments[b_idx] = intersected_parts[0]
            elif len(intersected_parts) > 1:
                assignments[b_idx] = min(
                    intersected_parts,
                    key=lambda pi: math.hypot(pt_xy.x() - centroids[pi].x(), pt_xy.y() - centroids[pi].y())
                )
            else:
                # 3. Orphan recovery (point outside due to buffer/sliver elimination/snapping)
                # Assign to nearest part by centroid distance
                assignments[b_idx] = min(
                    range(n_parts),
                    key=lambda pi: math.hypot(pt_xy.x() - centroids[pi].x(), pt_xy.y() - centroids[pi].y())
                )

    part_buildings: List[List[Dict[str, Any]]] = [[] for _ in range(n_parts)]
    for b_idx, p_idx in enumerate(assignments):
        part_buildings[p_idx].append(bldgs[b_idx])

    total_assigned = sum(len(pb) for pb in part_buildings)
    if total_assigned != len(bldgs) and fback:
        fback.pushWarning(
            f"[EA {parent_code}] Building assignment count mismatch: "
            f"{len(bldgs)} input buildings vs {total_assigned} assigned."
        )

    return part_buildings

