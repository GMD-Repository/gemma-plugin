# <img src="/icons/repair_geom.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> Geometry Repair Toolkit

The **Geometry Repair Toolkit** is an interactive topological inspection and repair suite designed to validate polygon geometries, eliminate vertex-level defects, recover missing boundaries, and bridge fragmented multipart polygons directly in QGIS edit mode. It operates both as a standalone dialog and as an embedded module within the **Check and Update** boundary management workflow.

## Access

- **Menu:** Gemma → Others → Geometry Repair Toolkit
- **Embedded Module:** Gemma → Updating of Boundaries → Check and Update (Tab 2: Geometry Check & Repair)
- **Component Algorithm IDs:** `gmd_pipeline:scangeometryerrors`, `gmd_pipeline:repairpolygongeometries`
- This tool operates as an interactive dialog directly modifying target layers in-place within active QGIS edit mode.

## When to Use

Use this toolkit when:

- Polygon layers contain invalid geometries, self-intersections, bowtie rings, or non-conforming geometry types.
- Digitize sessions introduce duplicate vertices, zero-length segments, or self-snapped nodes.
- Attribute records exist with null, missing, or empty geometry shapes that can be recovered from surrounding polygon boundaries.
- Administrative boundaries (such as barangays) are split into disconnected polygon parts that need to be merged into a single-part geometry by bridging only the gaps between them.
- Seam lines or stray vertices produce sharp spike collars or sliver holes that must be cleaned without altering authentic exterior boundaries.
- Pre-processing boundary datasets before running topological checks such as MBI Checker, MBI Validator, or Fill Polygon Gaps.

## Interface & Tab Architecture

The toolkit provides three functional tabs:

1. **Geometry Fixer (Tab 1)**: Multi-layer background scanning, interactive defect table, canvas rubber-band and vertex marker highlights, and automated in-place geometry repairs.
2. **Merge Polygon Parts (Tab 2)**: Interactive single-feature and batch multipart polygon gap bridging, seam despiking, sliver hole removal, and real-time color-coded canvas previews.
3. **Help and Information (Tab 3)**: Embedded reference manual covering error taxonomy, repair mechanisms, and operational best practices with adaptive light/dark theming.

## Geometry Fixer (Tab 1)

The **Geometry Fixer** tab scans one or more polygon layers for topological invalidities and executes targeted in-place repairs.

### Error Types Reference

The scanner evaluates layers against the following topology and geometry classifications:

| Error Type | Description | Repair Mechanism | Action Type |
|---|---|---|---|
| **Null Geometry** | Feature record exists in the table, but has no geometry object. | Spatial gap recovery from surrounding polygon boundaries | Auto-fixable |
| **Empty/Missing Geometry** | Feature geometry object exists but contains no coordinates or area. | Spatial void recovery from surrounding polygon boundaries | Auto-fixable |
| **Invalid Geometry** | Non-compliant GEOS geometry (spikes, folded edges, ring self-intersections). | Polygon reconstruction (unary union planarization and hole restoration) | Auto-fixable |
| **Self Intersection** | Polygon boundary intersects itself (e.g. bowtie or figure-8 ring). | Polygon reconstruction and planar face decomposition | Auto-fixable |
| **Invalid Geometry + Self Intersection** | Combined defect exhibiting general invalidity and boundary self-crossings. | Multi-stage polygon reconstruction | Auto-fixable |
| **Wrong-type Geometry** | LineString, Point, or GeometryCollection stored in a polygon layer. | Polygon component extraction and planar reconstruction | Auto-fixable |
| **Duplicate Vertex** | Duplicate or near-duplicate node created during digitization or self-snapping. | Progressive tolerance sweep ($10^{-12}$ to $10^{-6}$ bbox scale) and vertex deduplication | Auto-fixable |
| **Ring/Structure Error** | Valid in GEOS, but QGIS validator rejects ring arrangement (e.g. hole outside exterior ring, nested part). | Manual review required (no automatic node fix exists; correct using the Vertex Tool) | Manual Review |
| **Duplicate Geometry** | Two or more features share identical geometry. | Manual review and attribute deduplication | Manual Review |
| **Dangle (Loose End)** | Unclosed line segment or disconnected boundary node. | Manual review and vertex snapping | Manual Review |

### Fixer Workflow

1. **Select Input Layers**: In the left panel, check one or more polygon vector layers to evaluate.
2. **Execute Scan**: Click **Scan Layers** to run multi-threaded background checks across selected layers.
3. **Inspect Detected Errors**: The results table categorizes all identified defects:
   - **White rows**: Auto-fixable errors with selectable checkboxes.
   - **Grey rows**: Non-auto-fixable defects (e.g. Ring/Structure Errors, Duplicate Geometries) with disabled checkboxes.
4. **Locate on Canvas**: Double-click any row to zoom to the feature. The tool highlights the defect with a red bounding outline and places an `X` vertex marker at the exact error coordinate.
5. **Select Rows**: Use individual row checkboxes or click the column header checkbox to toggle all auto-fixable rows.
6. **Apply Repairs**: Click **Repair Selected Features**. The engine routes each feature to its appropriate repair worker:
   - Features resolved successfully are updated in the layer's edit buffer.
   - Features that cannot be resolved automatically (e.g. zero-area geometries that collapse to a line) are logged with specific diagnostic messages and tallied as **Needs manual review**.
7. **Verify and Commit**: Re-run **Scan Layers** while still in edit mode to verify that all errors are cleared. Use QGIS's **Save Edits** to persist changes or **Cancel Edits** to discard all modifications.

### Repair Mechanics & Limitations

- **Duplicate Vertex Removal**: Progressively sweeps coordinate deduplication tolerances scaled against the feature's bounding box diagonal ($10^{-12}$ to $10^{-6}$). Repaired geometries are re-validated before marking as fixed. If a ring contains fewer than 4 distinct points (a sub-millimetre self-snap forming a degenerate hole), automatic removal is prevented to avoid destroying the ring; the log identifies the ring for manual deletion via the Vertex Tool.
- **Multipart Slivers**: Polygon reconstruction resolves self-intersecting bowties by planarizing rings into individual faces. Artifact slivers with an area ratio below $0.1\%$ are automatically filtered out, while legitimate multipart components are preserved.
- **Unfixable Outlines**: Features whose boundaries collapse to a line enclose zero area and cannot be reconstructed into valid polygons. Operators must either redigitize or delete the record manually.

## Merge Polygon Parts (Tab 2)

The **Merge Polygon Parts** tab joins the disconnected components of a multipart polygon feature into a cohesive single-part polygon. It operates by bridging **only the gap between parts**, ensuring that untouched exterior perimeters, coastal boundaries, and vertex configurations remain unaltered.

### Mathematical & Topological Principle

The bridge engine uses a morphological closing operation constrained strictly to adjacent parts:

1. **Part Dissolve**: Individual parts are repaired and planarized. Overlapping or contiguous parts dissolve into coherent bodies.
2. **Closing Buffer**: The geometry is expanded by a half-gap buffer $+d$ and contracted by $-d$, where:
   $$d = \frac{\text{Gap Width}}{2}$$
3. **Bridge Filtering**: The difference between the closed geometry and original parts is calculated. Only bridge pieces that connect two or more parts are retained. Unwanted outward buffer expansion along open edges is discarded.
4. **Seam Despiking**: Vertices along the newly created seam that fold back sharper than the angle threshold are deleted.
5. **Sliver Hole Filling**: Residual seam holes smaller than the specified area threshold or having a hairline compactness ratio are filled:
   $$\text{Compactness} = \frac{4\pi \cdot \text{Area}}{\text{Perimeter}^2} < 0.1$$

### Configuration Parameters

| Parameter | Type / Range | Default | Description |
|---|---|---|---|
| **Layer** | Polygon Vector | Active Layer | Target polygon layer to inspect and edit. |
| **Gap Width** | Numeric ($0.1$ to $100,000\text{ m}$) | $30.0\text{ m}$ | Maximum distance bridged between disconnected parts. |
| **Auto Gap** | Checkbox | Enabled | Scans the minimum spanning tree distance between parts to compute the optimal bridge width. Capped at $100\text{ m}$ to prevent accidental merging of legitimate offshore islands or exclaves. |
| **Also fill edge notches** | Checkbox | Disabled | Bridges narrow inlets or notches along outer perimeters in addition to part gaps. Modifies the external outline. |
| **Remove spikes sharper than** | Numeric ($0.5^\circ$ to $45^\circ$) | $10.0^\circ$ | Deletes acute stray-vertex tails and inward slits along the seam. Protected nodes shared with neighboring features and spikes exceeding $2\%$ of ring area are never removed. |
| **Remove sliver holes smaller than** | Numeric ($0.01$ to $1,000,000\text{ m}^2$) | $10.0\text{ m}^2$ | Fills small interior voids or hairline seam gaps resulting from bridging. Authentic enclave holes (e.g. interior barangays) are retained. |
| **Live preview on map** | Checkbox | Enabled | Renders real-time color-coded rubber bands over the map canvas showing the projected merge result. |

### Canvas Preview Legend

When a feature is picked or highlighted from the scan table, the map canvas renders four distinct visual indicators:

- **Orange Fill** (`#ff7800`): The bridge area to be added between parts.
- **Dashed Red Outline** (`#dc0000`): The projected final boundary of the merged polygon.
- **Red X Markers** (`#dc0000`): Spike vertices flagged for removal.
- **Magenta Fill** (`#ff00ff`): Sliver interior holes that will be filled.

### Operating Modes

#### Mode 1: Interactive Single Feature Pick

1. Select the target polygon layer in **Settings**.
2. Click **Pick Feature on Map**, then click the desired multipart polygon on the canvas.
3. The tool flashes the feature, calculates the part count, and auto-detects the optimal gap width.
4. Review the canvas preview (orange bridge, dashed red outline, magenta holes, red X spikes).
5. Adjust **Gap width**, **Remove spikes**, or **Remove sliver holes** if necessary.
6. Click **Zoom** to center the map view on the feature.
7. Click **Apply Fix** to apply the merge in-place to the layer's edit buffer.
8. Click **Save Edits** to persist to disk, or **Undo** to revert the modification immediately.

#### Mode 2: Batch Scanning & Selective Fix

1. With the target layer selected, click **Scan All Features**.
2. The engine performs a non-destructive trial merge across all features in the layer without making any edits.
3. Review the **Scan Results** table:
   - **Checkbox**: Selection toggle (header checkbox selects or clears all fixable rows).
   - **Feature ID** & **Name**: Layer attributes identifying each polygon.
   - **Parts**: Part count transition (e.g. `2 → 1` or `3 → 2`).
   - **Gap Width**: Individual scanned bridge width for that feature.
   - **Area Change**: Net area added in $\text{m}^2$ or hectares ($\text{ha}$).
   - **Spikes & Holes**: Count of removed vertices and filled holes.
   - **Note**: Diagnostic status (e.g. parts remaining multipart due to distance $> 100\text{ m}$ shown in orange; features with zero change disabled).
4. Click any row to preview that specific feature on the canvas.
5. Untick any features that should remain multipart (such as offshore island barangays).
6. Click **Fix Checked (N)** to execute all selected repairs simultaneously as a single undoable edit transaction.
7. Click **Undo** to revert all batch fixes in one action, or **Save Edits** to commit to disk.

## Help and Information (Tab 3)

The **Help and Information** tab provides an integrated HTML reference manual embedded directly in the toolkit dialog. It renders reference tables, diagnostic explanations, and step-by-step guidance formatted with adaptive light/dark mode styling that matches the user's active QGIS desktop theme.

## In-Place Layer Editing & Safety Controls

The Geometry Repair Toolkit prioritizes data safety through non-destructive in-memory editing:

- **Active Edit Buffer**: All repairs are applied directly to the source layer within QGIS edit mode (indicated by a pencil icon on the layer). No redundant duplicate layers are created.
- **Single-Transaction Rollback**: Both individual feature repairs and batch fixes are registered in QGIS's edit buffer. Clicking **Undo** immediately reverses the modification.
- **Direct Save & Cancel**: Changes remain in memory until explicitly saved. Use the dialog's **Save Edits** button or QGIS's native editing toolbar to save changes permanently, or **Cancel Edits** to abandon all changes and restore the layer's original state.
- **Topology Pre-requisite**: Always run the Geometry Repair Toolkit to fix self-intersections and duplicate vertices prior to running topological boundary analysis (such as the MBI Checker or Fill Polygon Gaps).
