import math
import random
from typing import List, Dict, Any, Optional, Tuple

from qgis.core import (
    QgsGeometry,
    QgsWkbTypes,
    QgsSpatialIndex,
)

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
            best_part = min(parts, key=lambda p: gap_centroid.distance(p['geom'].centroid().asPoint()))
            
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
                lines.append(clipped)
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
