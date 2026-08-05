# <img src="/icons/check_and_update.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> Check and Update

The **Check and Update** tool provides a structured workflow for boundary management activities: **Georeferencing & Attributes Setup**, **Geometry Checking & Repair**, and **Updating Metadata**.


## Access

- **Menu:** Gemma → Updating of Boundaries → Check and Update
- **Component Algorithm IDs:** `gmd_pipeline:scangeometryerrors`, `gmd_pipeline:repairpolygongeometries`, `gmd_pipeline:join_barangay_attributes`, `gmd_pipeline:update_lgu_with_psgc`


## Workflow Sections

### Pre-Processing

The **Pre-Processing** tab provides a 3-step sequential workflow for spatial basemaps and attribute initialization:

1. **Georeferencing**:
   - Includes a dedicated action button **Open QGIS Georeferencer** to directly launch QGIS's built-in Georeferencer window for raster basemaps, scanned map sheets, or aerial imagery.

2. **Digitize**:
   - **PSA Reference Layer & Opacity**: Selects the PSA reference layer (auto-suggesting layers ending in `*_psa`) and configures layer transparency/opacity (`0% - 100%`, defaulting to `25%`) with an **Apply** button.
   - **Adjust Feature**: Populates all barangay features from the selected **PSA Reference Layer** using its `barangay` attribute column. Features **Edit**, **Previous**, **Next**, and **Done** buttons. Clicking **Edit** selects the feature on the canvas, zooms to its bounding box, opens the Vertex Tool, launches the core **Topology Checker** (configuring `must not have gaps`), minimizes the dialog, and displays a canvas banner (`Previous`, `Re-Edit`, `Next`, `Save & Done`, `Return`). On every **Next** or **Previous** step, **Validate All** is automatically triggered on the Topology Checker panel.

3. **Update and Verify**:
   - Launches **Run Join Barangay Attributes** (`gmd_pipeline:join_barangay_attributes`) to join tabular census data using fuzzy matching.
   - Launches **Run Update Metadata** (`gmd_pipeline:update_lgu_with_psgc`) to auto-populate LGU PSGC metadata, standard attribute schemas, and administrative codes.


### Geometry Check & Repair (Chronological Workflow)

1. **Target Layer & Check Error Options**: Choose polygon layer and select error check types (Null, Empty, Invalid GEOS, Self-Intersections, Wrong Type, Duplicates).
2. **Step 1: Scan Geometry Errors**: Runs `gmd_pipeline:scangeometryerrors` algorithm, automatically populates an interactive **Detected Errors Table** (`FID`, `Layer`, `Error Type`, `Description`, `Auto-fixable`), and loads the Point Error Layer into QGIS.
3. **Interactive Table Selection & Map Zoom**:
   - **Double-click** any row to zoom the QGIS map canvas directly to that error feature.
   - **Multi-select** specific rows to target specific features for repair.
4. **Step 2: Repair Polygon Geometries**:
   - If specific table rows are highlighted, repairs **only those selected error features**.
   - If no rows are selected, repairs **all detected errors** across the layer.
5. **Step 3: UPSERT Repaired Features to Layer**:
   - Merges the clean repaired geometries back into a complete updated version of the target polygon layer (`Updated_<layer_name>`).
   - Replaces defective features with clean repaired geometries while keeping all untouched valid features preserved.

