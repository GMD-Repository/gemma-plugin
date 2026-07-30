# Repair Polygon Geometries

The **Repair Polygon Geometries** algorithm reconstructs invalid, self-intersecting, or wrong-type polygon geometries and recovers null/empty polygon shapes into a clean vector output layer.

---

## Access

- **Processing Toolbox:** GMD Pipeline → GMD Toolkits → Repair Polygon Geometries

---

## When to Use

Use this algorithm when:

- Reconstructing invalid GEOS geometries or self-intersecting polygon boundaries.
- Recovering missing/null polygon shapes using surrounding boundary context.
- Running automated repairs on specific features identified during [Scan Geometry Errors](/tools/scan-geometry-errors).

---

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| **Input Polygon Layer** | Vector (Polygon) | Target vector polygon layer to repair. Supports native QGIS **Selected features only** option. |
| **Repair Mode** | Enum | • **Auto-Detect & Repair All Issues**<br>• **Reconstruct Invalid / Self-Intersecting / Wrong-Type Geometries Only**<br>• **Recover Null / Empty Geometries Only** |
| **Repaired Polygon Layer** | Vector Sink (Polygon) | Output vector polygon layer containing clean repaired geometries. |

---

## Selected Features Execution

This algorithm natively supports QGIS's **Selected features only** checkbox:
1. Run [Scan Geometry Errors](/tools/scan-geometry-errors) to identify problem features.
2. Select target features on the input polygon layer (using feature selection or matching `source_fid` from the error layer).
3. Open **Repair Polygon Geometries**, tick **Selected features only**, and execute the algorithm to repair only those selected features.

---

## Non-Destructive Memory Layers

All output features are written to a new **Repaired Polygon Layer** (or file destination). Your original source dataset is **never** modified during processing.
