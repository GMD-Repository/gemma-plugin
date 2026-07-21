# Geometry Repair Toolkit

The **Geometry Repair Toolkit** is a standalone dialog-based tool for validating and repairing polygon geometries. It provides a comprehensive interface for detecting and fixing common geometry issues across your polygon layers.

## Access

- **Menu:** GeMa → Tools → Geometry Repair Toolkit
- This tool opens as a **separate dialog window** (not through the Processing Toolbox).

## When to Use

Use this tool when:

- You suspect layers contain invalid or corrupted geometries
- QGIS reports geometry errors during processing operations
- You need to clean up polygon layers before running other tools
- You want to identify and fix duplicate, null, or wrong-type geometries

## Features

### Geometry Checker (Tab 1)

The checker scans your polygon layers for the following topology and geometry issues:

| Issue Type | Description |
|------------|-------------|
| **Duplicate Geometry** | Two or more features share the exact same geometry |
| **Invalid Geometry** | Polygons with self-intersections or other OGC validity errors |
| **Wrong-type Geometry** | Features whose geometry type doesn't match the layer's expected type |
| **Null Geometry** | Feature records that exist but have no geometry object |
| **Empty/Missing Geometry** | Features that exist but have no usable shape or coordinates |

### Issue Table

Detected issues are displayed in an interactive table with:

- **Checkable rows** — Select which issues to auto-fix using checkboxes
- **Header checkbox** — Select/clear all auto-fixable rows at once
- **Issue details** — Feature ID, layer name, issue type, and description
- **Zoom-to-feature** — Click on a row to zoom the map to the affected feature

### Auto-Fix Capabilities

For supported issue types, the toolkit can automatically apply fixes:

- **Invalid geometries** — Repaired using QGIS's built-in geometry repair algorithms
- **Null/Empty geometries** — Flagged for removal or manual review
- **Duplicate geometries** — Identified for manual deduplication

### Visual Highlighting

When you select an issue in the table, the affected geometry is highlighted on the map using:

- **Rubber bands** — Colored overlays showing the exact error location
- **Vertex markers** — Point markers on specific problematic vertices

## Interface

The toolkit uses a tabbed interface:

1. **Tab 1 — Geometry Checker** — Scan layers and review detected issues
2. Additional tabs may be available for specialized repair operations

## How to Use

1. Open the Geometry Repair Toolkit from **GeMa → Tools → Geometry Repair Toolkit**
2. Select the polygon layers you want to check from the layer list
3. Click **Run** to start the geometry scan
4. Review the detected issues in the results table
5. Check the boxes next to issues you want to auto-fix
6. Click **Fix Selected** to apply repairs
7. Verify the fixes by re-running the checker

::: tip
Run the Geometry Repair Toolkit on your layers **before** using other processing tools like the MBI Checker or Fill Polygon Gaps. Invalid geometries can cause unexpected results in those tools.
:::

::: warning
Auto-fix operations modify your layer data. Make sure to save a backup or work on a copy of your layers before applying fixes.
:::
