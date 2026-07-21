# Fill Polygon Gaps

The **Fill Polygon Gaps** tool automatically fills gaps between barangay polygons by assigning uncovered areas to the correct neighboring polygon. It supports a **preview-before-apply** workflow, allowing you to inspect proposed gap fills before committing changes.

## Access

- **Processing Toolbox:** GMD Pipeline → 1Map → Fill Polygon Gaps
- **Algorithm ID:** `gmd_pipeline:fill_polygon_gaps`

## When to Use

Use this tool when:

- The MBI Checker has identified gaps between barangay boundaries
- You need to assign uncovered areas to the correct adjacent barangay
- You want to preview gap fills before applying them to the data

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| **Input Layer** | Vector Layer (Polygon) | The barangay boundary polygon layer containing gaps |
| **Label Field** | Field | The attribute field used to identify each polygon (e.g., barangay name) |
| **Polygon Identifier Value** | Custom Dropdown | Select the specific polygon to fill gaps for — populated dynamically from the label field |
| **Extent Mode** | Dropdown | Choose between `Manual Extent` or `Extent Layer` to define the working area |
| **Extent** | Extent | Manual extent for the analysis area (when using Manual Extent mode) |
| **Extent Layer** | Vector Layer | A layer whose extent defines the analysis area (when using Extent Layer mode) |

## How It Works

1. **Extent Definition** — The tool determines the working area either from a manual extent or from the bounding box of an extent layer.
2. **Feature Filtering** — Only polygons intersecting the defined extent are considered, improving performance for large datasets.
3. **Gap Detection** — The tool identifies empty areas between the selected polygon and its neighbors within the extent.
4. **Gap Assignment** — Gaps are assigned to the nearest polygon based on spatial proximity.
5. **Preview** — Results are displayed as a categorized layer so you can inspect the proposed assignments.
6. **Apply** — Once satisfied, apply the changes to update the polygon boundaries.

## Dynamic Dropdown

The **Polygon Identifier Value** parameter uses a custom widget that dynamically updates its choices based on:

- The selected **Input Layer**
- The selected **Label Field**
- The current **Extent** (only values from features intersecting the extent are listed)

This makes it easy to work with specific areas without scrolling through large value lists.

## Output

- A gap-filled polygon layer with categorized styling showing which gaps were assigned to which barangay
- Color-coded results for easy visual validation

::: tip
Use the **Extent Layer** mode when you want to focus on a specific city or municipality. Load the municipal boundary and select it as the extent layer — only barangays within that area will be processed.
:::

::: warning
Always review the gap fill results carefully before committing changes. Automated gap assignment is based on spatial proximity and may not always match the intended administrative boundary.
:::
