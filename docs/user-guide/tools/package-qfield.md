# Package for QField

The **Package for QField** tool packages your QGIS project and its spatial data for field data collection using **QField** — a mobile GIS application. It creates self-contained project packages trimmed physically to selected administrative or enumeration boundaries (EA or Barangay Level) that can be deployed on Android and iOS devices for offline fieldwork.

---

## Access

- **Menu:** Gemma → QField → Package for QField
- **Toolbar:** Gemma Toolbar → Package for QField icon
- **Shortcut:** `Ctrl+Alt+Q`

---

## When to Use

Use this tool when:

- Preparing QGIS projects for census enumeration, survey data collection, or field verification using QField.
- You need lightweight, offline-capable project packages physically trimmed to specific **EA** or **Barangay** boundaries.
- Configuring layer roles, QField editing permissions (writable vs read-only), raster basemaps, and custom export file formats (`.geojson`, `.gpkg`, `.shp`, `data.gpkg`).

---


## How to Use

Follow this step-by-step guide to package your QGIS project for QField.

### Step 1: Open QGIS & Launch the Tool

1. Open QGIS and load your active mapping project containing your vector layers and basemaps.
2. Launch the tool using one of the following methods:
   - **Menu Bar:** Click **Gemma → QField → Package for QField**.
   - **Toolbar:** Click the **Package for QField** icon on the Gemma Toolbar.
   - **Keyboard Shortcut:** Press `Ctrl+Alt+Q`.
3. **Help Button:** Notice the **Help** button located at the top-right header of the dialog. Clicking it immediately opens this online documentation page in your web browser for quick reference.

---

### Step 2: Configure Global Settings (`⚙ Configuration`)

Click the **⚙ Configuration** button in the upper header to open the global settings dialog:

#### A. Export Directory
Select the destination folder on your computer where the packaged QField project folders will be generated.

#### B. Raster Configuration
Configure offline satellite imagery and basemap clipping settings:

1. **Satellite Image Source Format**: Select the format of your source satellite imagery:
   - `GeoPackage (*_img.gpkg)`: Looks for source rasters named `{pppmm}_img.gpkg`.
   - `MBTiles (*_img.mbtiles)`: Looks for source rasters named `{pppmm}_img.mbtiles`.
   - `Both GPKG and MBTiles`: Checks for GeoPackage first, then falls back to MBTiles. Also unlocks the Additional Raster Directory.
2. **Satellite Image Directory**: Browse to the folder containing your municipality-level satellite images. Files must follow the naming convention `{pppmm}_img.gpkg` or `{pppmm}_img.mbtiles` *(where `{pppmm}` is the 5-digit PSGC Province/Municipality code, e.g. `05017_img.gpkg`)*.
3. **Convert satellite to MBTiles**: Check this box to automatically convert the clipped satellite output into an optimized `.mbtiles` format for faster performance on mobile devices.
4. **Additional Raster Directory**: *(Optional)* Select a directory containing secondary `.mbtiles` basemaps named `{pppmm}.mbtiles`.

#### C. Layer Properties (Data Sources Table)
Customize editing actions, visibility behavior, and output file formats per layer role:

- **QField Action**:
  - `Offline Editing`: Makes vector layers editable in QField (for field data entry).
  - `Copy / Read-Only`: Keeps layers as read-only background reference data.
- **Identifiable Checkbox (`✓`)**: Determines if feature attributes pop up when tapped in QField.
- **Read-Only Checkbox (`✓`)**: Locks or unlocks layer editing permissions.
- **Searchable Checkbox (`✓`)**: Enables searching for layer features using QField's search bar.
- **Export Format**: Choose the output file format for each role:
  - `(data.gpkg)`: Bundles reference layers into a single combined GeoPackage dataset.
  - `.geojson`: Standalone GeoJSON format.
  - `.gpkg`: Standalone GeoPackage file format.
  - `.shp`: Standalone ESRI Shapefile dataset.

#### D. Restore Defaults
Click **Restore Defaults** if you want to reset all configuration settings back to factory default values. Click **Close** when finished.

---

### Step 3: Prepare Project Layers, Hierarchy & Styles

Return to the main dialog tabs to organize layer structure and apply symbology styles:

#### A. Output Selection Level
In the top dropdown, select your target packaging level:
- **EA Level**: Packages maps trimmed to 14-digit Enumeration Area boundaries (`05017160100001`).
- **Barangay Level**: Packages maps trimmed to 8-digit Barangay boundaries (`05017160`).

#### B. Managing Layer Groups & Reordering
Use the **Layer Groups & Styles** tree panel to organize layers into folders:

1. **Add Group**: Type a folder name into the text box and click **`[+]`** (Add Group).
2. **Delete Item**: Select a group or layer and click **`[-]`** (Delete Group).
3. **Multi-Selection**:
   - `Shift + Click`: Select a contiguous range of layers or group folders.
   - `Ctrl + Click`: Select multiple non-adjacent layers or group folders.
4. **Drag & Drop**: Click and drag selected layers into any group folder.
5. **Keyboard Shortcuts**:
   - `Alt + Up`: Move selected item **UP**.
   - `Alt + Down`: Move selected item **DOWN**.
   - `Alt + Left`: Move selected item **OUT** to parent level.
   - `Alt + Right`: Move selected item **IN** into the preceding group folder.
6. **Layer Visibility Checkboxes (`✓`)**: Check or uncheck the box next to any layer to set whether it is visible by default when opened in QField.

#### C. Assigning Roles & QML Styles
- **Assigned Role**: Select the functional role for each layer (e.g. `Building points`, `Barangay layer`, `Road layer`).
- **QML Style**: Select a QML symbology style file to apply. The tool automatically detects matching styles based on layer names. Click **Import QML Style(s)...** to import custom `.qml` files from your computer.

#### D. Using Layout Presets
- **`📂 Load Preset`**: Load standard built-in templates (`Form 2 Layout`, `Form 8 Layout`) or custom user-saved layouts.
- **`💾 Save Preset`**: Save your current folder structure and QML assignments into a named preset for quick re-use in future projects.
- **`🗑 Delete Preset`**: Delete custom user-saved presets.

#### E. Apply to QGIS Project
Click **▶ Create Groups and Apply Style** to restructure your active QGIS project's Layers panel and apply QML symbology styles directly.

---

### Step 4: Select Target Administrative Areas (Process Settings)

1. **Select City/Municipality Tree**: Expand the regional tree filter or type in the search bar to locate your target City, Municipality, or Barangay.
2. **Select All / Deselect All**: Use the **Select All** or **Deselect All** buttons to quickly check or uncheck administrative units in bulk.
3. **Select BGYs/EAs to Process**: Review the list of target areas generated for export.

---

### Step 5: Package and Export

1. **Single Export**: Click **Export** to generate the packaged QField project folder for the currently selected area.
2. **Next Geocode**: Click **Next Geocode** to step to the next area in the list.
3. **Batch Export**: Click **Batch Run** to automatically package all selected areas sequentially without manual intervention.
4. **Clear Filter Button**: Click **Clear Filter** at any point to undo active spatial subset filters and reset the QGIS map canvas back to the full municipality view.

After export completes, copy the generated project folder from your Export Directory to your mobile device (Android or iOS) and open the `.qgz` project file in **QField** to begin field data collection.



## Key Technical Features

### 1. Physical Feature Trimming & Spatial Clipping
During export, vector layers are physically trimmed to contain **only the features matching the target EA or Barangay**. Out-of-area features are excluded, yielding lightweight, fast-loading files for mobile devices.

### 2. QField Custom Properties Metadata
Packaged project layers include QGIS `<customproperties>` metadata that instruct QField and QFieldSync on device behavior and synchronization:

- **`QFieldSync/action`** (`offline`, `copy`, `no_action`): Sets offline editing vs background read-only mode in QField.
- **`remoteSource`** & **`remoteLayerId`**: Stores the original desktop master file path so QFieldSync can merge field edits back into master databases.
- **`QFieldSync/sourceDataPrimaryKeys`** (`fid`): Identifies primary key attributes for feature matching.
- **`QFieldSync/photo_naming`**: Manages naming rules for geotagged photos taken in QField.

### 3. Assigned Role Suffix & Naming Rules
Exported filenames follow standard role suffixes based on your Assigned Role configuration:

| Assigned Role | Suffix Rule | Output Filename (e.g., EA `04920005001000`) |
| :--- | :--- | :--- |
| **Geotagging Layer** | **No Suffix** *(geocode only)* | `04920005001000.shp` *(or .geojson)* |
| **Building points** | `*_bldg_point` | `04920005001000_bldg_point.geojson` |
| **Barangay layer** | `*_bgy` | `04920005001000_bgy.geojson` *(or data.gpkg)* |
| **EA layer** | `*_ea` | `04920005001000_ea.gpkg` *(or data.gpkg)* |
| **Landmark layer** | `*_landmark` | `04920005001000_landmark.gpkg` *(or data.gpkg)* |
| **Block layer** | `*_block` | `04920005001000_block.gpkg` *(or data.gpkg)* |
| **Road layer** | `*_road` | `04920005001000_road.gpkg` *(or data.gpkg)* |
| **River layer** | `*_river` | `04920005001000_river.gpkg` *(or data.gpkg)* |
| **Bridge layer** | `*_bridge` | `04920005001000_bridge.gpkg` *(or data.gpkg)* |
| **Railroad layer** | `*_railroad` | `04920005001000_railroad.gpkg` *(or data.gpkg)* |

*Note: If an optional layer (such as Block or Railroad) is not present in the active QGIS project, the export engine gracefully skips it without throwing errors.*

::: tip
Always verify your packaged project on a test mobile device before deploying to field enumerators. Ensure all layers load properly, satellite basemaps display correctly, and offline editing forms function as intended.
:::
