# <img src="/icons/scan_errors.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> Scan Geometry Errors

The **Scan Geometry Errors** algorithm scans an input vector polygon layer for specific geometry and topology defects and outputs a Point vector sink layer representing exact error locations and audit metadata.


## Access

- **Processing Toolbox:** GMD Pipeline → GMD Toolkits → Scan Geometry Errors
- **Algorithm ID:** `gmd_pipeline:scangeometryerrors`


## When to Use

Use this algorithm when:

- Auditing polygon layers for topological errors prior to boundary management or processing.
- Generating a standalone spatial Error Layer (Point geometry) for styling, visual inspection, or GIS report generation.
- Performing automated batch validation of polygon layers across project folders or scripts.


## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| **Input Polygon Layer** | Vector (Polygon) | Target vector polygon layer to scan. |
| **Check Null Geometries** | Boolean | Detect features with null geometry objects (`True`/`False`). |
| **Check Empty Geometries** | Boolean | Detect features with empty geometry shapes (`True`/`False`). |
| **Check Invalid Geometries (GEOS)** | Boolean | Detect features failing GEOS validity tests (`True`/`False`). |
| **Check Self Intersections** | Boolean | Detect features with self-intersecting polygon boundaries (`True`/`False`). |
| **Check Wrong Geometry Types** | Boolean | Detect non-polygon geometries in the layer (`True`/`False`). |
| **Check Duplicate Geometries** | Boolean | Detect features sharing exact duplicate geometries (`True`/`False`). |
| **Error Locations (Point Layer)** | Vector Sink (Point) | Output point layer containing precise error locations and metadata. |


## Output Error Layer Schema

The resulting **Error Locations** point layer includes the following fields:

| Field Name | Type | Description |
|------------|------|-------------|
| `source_fid` | Integer | Feature ID of the source feature containing the error. |
| `layer_name` | String | Name of the source layer scanned. |
| `error_type` | String | Type of error (e.g. `Invalid Geometry`, `Null Geometry`, `Self Intersection`). |
| `description` | String | Detailed explanation of the detected issue. |
| `is_autofixable` | Boolean | Indicates whether the issue can be automatically resolved by the Repair algorithm. |


## Next Steps

Use the generated **Error Locations** layer to inspect issues visually in QGIS or pass the target layer to the [Repair Polygon Geometries](/tools/repair-polygon-geometries) processing tool to fix selected error features.
