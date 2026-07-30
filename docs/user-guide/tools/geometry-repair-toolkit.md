# <img src="/icons/reports.png" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> Geometry Repair Toolkit

The **Geometry Repair Toolkit** is a standalone dialog-based tool for validating, inspecting, and repairing polygon geometries. It provides a comprehensive interface for detecting and fixing common topology and geometry issues across your polygon layers into safe, temporary memory output layers.

---

## Access

- **Menu:** Gemma → Others → Geometry Repair Toolkit
- This tool opens as a **separate dialog window** (not through the Processing Toolbox).

---

## When to Use

Use this tool when:

- You suspect polygon layers contain invalid, self-intersecting, or corrupted geometries.
- QGIS reports geometry errors during processing or spatial operations.
- You need to clean up and validate polygon layers before running other GMD tools (such as MBI Checker or Fill Polygon Gaps).
- You want to identify and fix null geometries, empty shapes, wrong geometry types, or duplicate features.

---

## Features & Tab Structure

The toolkit features a tabbed interface:
1. **Geometry Fixer (Tab 1)** — Scan layers, inspect detected issues in an interactive table, highlight error geometries on the map canvas, and run automated repairs.
2. **Help and Information (Tab 2)** — View reference tables for error types, repair mechanisms, output layer behavior, and limitations.

---

## Error Types Reference

The toolkit scans polygon layers for the following topology and geometry issues:

| Error Type | Description | Repair Mechanism |
|------------|-------------|------------------|
| **Null Geometry** | The feature record exists, but there is no geometry object. | Auto-fixable (Recovery from surrounding polygons) |
| **Empty/Missing Geometry** | The feature exists, but its geometry has no usable shape or coordinates. | Auto-fixable (Recovery from surrounding polygons) |
| **Invalid Geometry** | The polygon has geometry errors such as self-intersection, ring error, spike, or folded edge. | Auto-fixable (Polygon reconstruction) |
| **Self Intersection** | The polygon crosses itself. | Auto-fixable (Polygon reconstruction) |
| **Wrong-type Geometry** | The feature's geometry type does not match the layer's declared geometry type (e.g. a line or GeometryCollection stored in a polygon layer). | Auto-fixable (Polygon reconstruction) |
| **Duplicate Geometry** | Two or more features share the exact same geometry. | Requires manual review / deduplication |
| **Dangle (Loose End)** | A line endpoint doesn't connect to any other line. | Requires manual review |

---

## How to Use

1. Open the tool from **Gemma → Others → Geometry Repair Toolkit**.
2. Under **Input Layers**, select one or more polygon layers to check.
3. Click **Scan Layers** to initiate the background geometry scan.
4. Review the detected errors in the results table:
   - **White rows**: Auto-fixable issues.
   - **Grey rows**: Issues requiring manual review.
5. Double-click any row to zoom to the affected feature on the map. The toolkit places rubber-band outlines and vertex markers over problematic geometry locations.
6. Check the rows to repair (or click the checkbox in the first column header to select/clear all auto-fixable rows).
7. Click **Repair Selected Features**. The toolkit routes each checked row to its specific repair mechanism and creates a new temporary repaired memory output layer.
8. Re-run **Scan Layers** on the temporary output layer to verify all errors are resolved.

---

## Repair Mechanisms & Output Layers

### Repair Selected Features
When you click **Repair Selected Features**, the tool inspects each checked error row and automatically applies the appropriate repair mechanism:
- **Invalid / Wrong-type / Self Intersection**: Reconstructs the polygon shape and writes the result to a new temporary output layer.
- **Null / Empty / Missing Geometry**: Recovers missing shapes using spatial boundary context from surrounding polygons.

### Multipart Resolution & Artifact Cleanup
Polygon reconstruction can occasionally leave a feature as a multipart polygon even if it started as a single part. When this occurs:
- The toolkit runs **Multipart to Singleparts** on only the touched features.
- Negligible fragment slivers resulting from reconstruction artifacts are automatically dropped.
- Genuine multi-part survivors sharing original feature attributes are re-merged back into a single multipart feature (preventing attribute row duplication).
- Pre-existing legitimate multipart features (such as a barangay with offshore islands) that were not repaired remain completely untouched.

### Non-Destructive Memory Layers
- **Original Source Data Protection**: Source layers are **never** modified. All fixes create temporary memory layers.
- **Attribute Field Preservation**: Temporary output layers retain all original attribute fields for seamless export.
- **Logging**: The log panel records layer names, processed feature IDs, repair methods, recovery status, and notes.

---

## Limitations & Review Best Practices

::: tip Recommended Workflow
Run the **Geometry Repair Toolkit** on your layers **before** using other processing tools like the MBI Checker or Fill Polygon Gaps. Invalid geometries can cause unexpected results in topological analysis.
:::

::: info Non-Destructive Operations
The toolkit always writes repaired features to new **temporary memory layers**. Your original input files/layers are never overwritten.
:::

::: warning Limitations & Manual Review
- **Visual Inspection**: Always visually inspect the resulting temporary output layer before exporting or replacing source data.
- **Re-Scan Verification**: Run **Check Validity** or re-scan the output layer with **Scan Layers** to confirm no secondary errors remain.
- **Deleted Feature Records**: Completely deleted attribute records cannot be recovered by this tool.
- **Edge Polygons**: Edge polygons cannot be safely reconstructed when their outer boundary is unknown. If an edge polygon is missing, return it to the LGU for corrected boundary geometry.
- **Manual Review**: Complex topology issues such as Duplicate Geometry and Dangles require manual review and editing.
:::
