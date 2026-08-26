# <img src="/icons/repair_geom.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> Geometry Repair Toolkit

The **Geometry Repair Toolkit** is a standalone dialog-based tool for validating, inspecting, and repairing polygon geometries. It provides a comprehensive interface for detecting and fixing common topology and geometry issues across polygon layers directly within QGIS.

## Access

- **Menu:** Gemma → Others → Geometry Repair Toolkit
- **Component Algorithm IDs:** `gmd_pipeline:scangeometryerrors`, `gmd_pipeline:repairpolygongeometries`
- This tool opens as a **separate dialog window** (not through the Processing Toolbox).

## When to Use

Use this tool when:

- You suspect polygon layers contain invalid, self-intersecting, or corrupted geometries.
- QGIS reports geometry errors during processing or spatial operations.
- You need to clean up and validate polygon layers before running other GMD tools (such as MBI Checker or Fill Polygon Gaps).
- You want to identify and fix duplicate vertices, null geometries, empty shapes, wrong geometry types, or duplicate features.

## Features & Tab Structure

The toolkit features a tabbed interface:
1. **Geometry Fixer (Tab 1)** — Scan layers, inspect detected issues in an interactive table, highlight error geometries on the map canvas, and run automated repairs.
2. **Help and Information (Tab 2)** — View reference tables for error types, repair mechanisms, layer edit behavior, and limitations.

## Error Types Reference

The toolkit scans polygon layers for the following topology and geometry issues:

| Error Type | Description | Repair Mechanism |
|------------|-------------|------------------|
| **Null Geometry** | The feature record exists, but there is no geometry object. | Auto-fixable (Recovery from surrounding polygons) |
| **Empty/Missing Geometry** | The feature exists, but its geometry has no usable shape or coordinates. | Auto-fixable (Recovery from surrounding polygons) |
| **Invalid Geometry** | The polygon has geometry errors such as ring errors, spikes, or folded edges. | Auto-fixable (Polygon reconstruction) |
| **Self Intersection** | The polygon boundary crosses itself (e.g. bowtie rings). | Auto-fixable (Polygon reconstruction) |
| **Invalid Geometry + Self Intersection** | Combined report when a feature exhibits both general invalidity and self-intersection. | Auto-fixable (Polygon reconstruction) |
| **Duplicate Vertex** | An accidental self-snap or zero-length segment created during manual digitizing. | Auto-fixable (Direct duplicate vertex removal) |
| **Wrong-type Geometry** | The feature's geometry type does not match the layer's declared geometry type (e.g. a line or GeometryCollection stored in a polygon layer). | Auto-fixable (Polygon reconstruction) |
| **Duplicate Geometry** | Two or more features share the exact same geometry. | Requires manual review / deduplication |
| **Dangle (Loose End)** | A line endpoint doesn't connect to any other line. | Requires manual review |

## How to Use

1. Open the tool from **Gemma → Others → Geometry Repair Toolkit**.
2. Under **Input Layers**, select one or more polygon layers to check.
3. Click **Scan Layers** to initiate the background geometry scan.
4. Review the detected errors in the results table:
   - **White rows**: Auto-fixable issues.
   - **Grey rows**: Issues requiring manual review.
5. Double-click any row to zoom to the affected feature on the map. The toolkit places rubber-band outlines and vertex markers over problematic geometry locations.
6. Check the rows to repair (or click the checkbox in the first column header to select/clear all auto-fixable rows).
7. Click **Repair Selected Features**. The toolkit routes each checked row to its specific repair mechanism and applies changes in-place.
8. Re-run **Scan Layers** on the layer to verify all errors are resolved before saving.

## Repair Mechanisms & In-Place Editing

### Repair Selected Features
When you click **Repair Selected Features**, the tool inspects each checked error row and automatically applies the appropriate repair mechanism directly to the original layer:
- **Duplicate Vertex**: Removes duplicate or near-duplicate vertices directly without requiring full polygon reconstruction.
- **Invalid / Wrong-type / Self Intersection**: Reconstructs the polygon shape to resolve geometry errors and self-intersections.
- **Null / Empty / Missing Geometry**: Recovers missing shapes using spatial boundary context from surrounding polygons.

### Multipart Resolution & Artifact Cleanup
Polygon reconstruction can occasionally leave a feature multipart even if it started as a single part (such as resolving a self-intersecting bowtie ring). When this occurs:
- Negligible fragment slivers resulting from reconstruction artifacts are automatically dropped.
- Genuine multi-part survivors sharing original feature attributes remain merged as a single multipart feature.
- Pre-existing legitimate multipart features (such as a barangay with offshore islands) that were not repaired remain completely untouched.

### In-Place Editing & Unsaved Changes Guard
- **Direct Layer Editing**: Repaired features are edited directly on the source layer in QGIS edit mode (indicated by a pencil icon and modified marker).
- **Safe Discard**: Changes remain unsaved in memory until you choose **Save Edits** or **Cancel Edits** from the QGIS Layer menu or editing toolbar.
- **Schema Preservation**: Attribute fields and schemas are preserved without adding unnecessary tracking columns. Recovery details, repair methods, and notes are logged in the execution console.

## Limitations & Review Best Practices

::: tip Recommended Workflow
Run the **Geometry Repair Toolkit** on your layers **before** using other processing tools like the MBI Checker or Fill Polygon Gaps. Invalid geometries can cause unexpected results in topological analysis.
:::

::: info In-Place Editing
The toolkit applies repairs directly to the layer in edit mode. Always use **Save Edits** to persist changes to disk or **Cancel Edits** to revert unwanted modifications.
:::

::: warning Limitations & Manual Review
- **Visual Inspection**: Always visually inspect repaired features before saving edits.
- **Re-Scan Verification**: Re-scan the layer with **Scan Layers** while still in edit mode to confirm no secondary errors remain.
- **Deleted Feature Records**: Completely deleted attribute records cannot be recovered by this tool.
- **Edge Polygons**: Edge polygons cannot be safely reconstructed when their outer boundary is unknown. If an edge polygon is missing, return it to the LGU for corrected boundary geometry.
- **CRS Sensitivity**: Validity is evaluated in the layer's native CRS. Because coordinate reprojection can shift vertices and alter geometry validity, re-run **Scan Layers** whenever a layer is reprojected.
- **Manual Review**: Complex topology issues such as Duplicate Geometry and Dangles require manual review and editing.
:::
