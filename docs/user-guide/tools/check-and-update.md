# <img src="/icons/check_and_update.svg" width="32" height="32" style="vertical-align: middle; display: inline-block; margin-right: 8px;" /> Check and Update

The **Check and Update** tool provides a complete, unified workflow for administrative boundary management: **Georeferencing & Digitizing Navigation**, **PSGC Geocode Left-Join Metadata Enrichment**, and **Chronological Geometry Error Scanning & Repair**.


## Access

- **Menu:** Gemma → Updating of Boundaries → Check and Update
- **Component Algorithm IDs:** `gmd_pipeline:scangeometryerrors`, `gmd_pipeline:repairpolygongeometries`, `gmd_pipeline:join_barangay_attributes`, `gmd_pipeline:update_lgu_with_psgc`, `gmd_pipeline:update_lgu_by_geocode`


## Workflow Sections

### Pre-Processing Workflow

The **Pre-Processing** tab contains a 3-step sequential interface (`Georeferencing  ➔  Digitize  ➔  Update and Export`):

#### 1. Georeferencing
- **Open QGIS Georeferencer**: Launches QGIS's built-in Georeferencer window directly from the plugin dialog to align raster basemaps, scanned map sheets, or aerial imagery to ground control points (GCPs) with default working directory set to `C:\PSA-GIS`.

#### 2. Digitize & Navigation
- **PSA Reference Layer & Opacity**: Selects the active PSA reference polygon layer (automatically suggesting layers ending in `*_psa`). Adjust layer transparency (`0%` to `100%`, defaulting to `25%`) with the **Apply** button to overlay boundary features clearly over raster basemaps.
- **Adjust Feature Selection**: Dropdown automatically lists all barangay features from the active reference layer using its `barangay` attribute column.
- **Feature Editing Controls**:
  - **Edit**: Activates digitizing mode for the highlighted feature. Automatically:
    - Zooms the map canvas directly to the feature's bounding box.
    - Opens the QGIS Vertex Tool for node editing.
    - Activates the **Feature Edit Guard**, locking vertex edits strictly to the active feature ID and automatically reverting accidental vertex edits on neighboring polygons.
    - Configures **Advanced Snapping** (12.0px tolerance, Vertex & Segment, Topological Editing, Self-Snapping enabled, Intersection Snapping disabled, Avoid Overlap).
    - Ensures the QGIS Topology Checker plugin is enabled and loaded into memory, displaying the panel when editing starts.
    - Minimizes the main dialog window and displays the dockable **Gemma Digitize Navigation Panel** (`DigitizeDockWidget`) in the lower-left workspace (providing `Previous`, `Next`, `Save (Done)`, `Return`, and feature selector dropdown).
  - **Previous / Next**: Cycles through features in alphabetical/sequential order, re-zooms map canvas automatically, and triggers **Validate All** on the Topology Checker dock panel.
  - **Save (Done)**: Concludes the digitizing session, prompting the user to **Save**, **Discard**, or **Cancel** pending revisions.

#### 3. Update and Export
- **Embedded Parameter Controls**:
  - **Layer Selection**: Reuses the **PSA Reference Layer** selected in Step 2 (*Digitize*), eliminating duplicate layer selection fields.
  - **LGU Geocode Field**: Dropdown auto-detects and suggests candidate geocode fields (e.g. `geocode`, `psgc`, `code`, `lgu_code`).
  - **LGU Barangay Name Field**: Dropdown auto-detects and suggests candidate barangay name fields (e.g. `barangay`, `lgu_bgy_name`, `brgy_name`).
  - **Hidden Defaults**: Uses standard default values behind the scenes (`Source = 'LGU'`, `Source Year = '2026'`, `Open Output = True`).
  - **Smart Folder Resolution**: Automatically saves the GeoPackage output into the physical directory folder of the input layer on disk. If the layer is a temporary memory layer, it falls back to the QGIS Project directory or user's Documents folder.
- **Action Button (`Update & Export (as GPKG)`)**:
  - **Immediate Visual UX Feedback**: Disables the button on click, updates text to `"Updating & Exporting... Please wait..."`, applies a busy visual style, sets mouse cursor to `Qt.WaitCursor` (spinner/hourglass), and forces an immediate UI repaint via `processEvents()`.
  - **8-Digit Concatenated Key Matching**: Matches the first 8 characters of the LGU layer geocode against the concatenated PSGC reference key (`province_code` + `city_mun_code` + `barangay_code`, e.g. `801` + `00` + `001` $\rightarrow$ `80100001`), supporting 8, 9, and 10-digit geocodes seamlessly.
  - **Browser-Style Auto-Numbering**: If the output file (e.g. `00509_bgy.gpkg`) already exists or is locked in QGIS, it automatically creates `00509_bgy (1).gpkg`, `00509_bgy (2).gpkg`, etc. without crashing or throwing OGR file locked errors.
  - **Database NULL Handling**: Populates unmatched or empty fields (`remarks`, `hhcount`, `bldgcount`, `bdry_status`) with database `NULL` (`QVariant()`) values instead of empty strings.
  - **16-Field Output Schema**: Outputs standard attribute schemas: `fid` (Integer), `map_uuid` (String, 36), `geocode` (String, 50, preserved from input LGU layer), `region` (String, 100), `province` (String, 100), `city_mun` (String, 100), `barangay` (String, 100), `code` (String, 50, defaulted to `'1003'`), `remarks` (String, 255, `NULL`), `source` (String, 100, `'LGU'`), `hhcount` (Integer, `NULL`), `bldgcount` (Integer, `NULL`), `sy` (String, 10, `'2026'`), `boundary` (String, 20, `'Barangay'`), `lgu_bgy_name` (String, 100), and `bdry_status` (String, 20, `NULL`).


### Geometry Check & Repair Workflow

The **Geometry Check & Repair** tab provides a 3-step chronological workflow for scanning, inspecting, and repairing defective polygon geometries:

1. **Target Layer & Check Error Options**: Choose the target polygon vector layer and select error types to evaluate (Null, Empty, Invalid GEOS, Self-Intersections, Wrong Geometry Type, Duplicate Geometries).
2. **Step 1: Scan Geometry Errors**:
   - Executes `gmd_pipeline:scangeometryerrors`.
   - Populates an interactive **Detected Errors Table** (`FID`, `Layer`, `Error Type`, `Description`, `Auto-fixable`).
   - Loads a Point Error Layer (`Geometry_Errors_<layer_name>`) into QGIS for spatial visualization.
3. **Interactive Table Selection & Canvas Zoom**:
   - **Double-click** any table row to zoom the QGIS map canvas directly to that defect.
   - **Multi-select** specific table rows to target specific error features for repair.
4. **Step 2: Repair Polygon Geometries**:
   - Executes `gmd_pipeline:repairpolygongeometries`.
   - If specific table rows are highlighted, repairs **only those selected features**.
   - If no rows are selected, repairs **all detected errors** across the layer.
5. **Step 3: UPSERT Repaired Features to Layer**:
   - Merges clean repaired geometries into a complete updated version of the target polygon layer (`Updated_<layer_name>`).
   - Replaces defective features while preserving all untouched valid features.

