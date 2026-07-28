# Package for QField

The **Package for QField** tool packages your QGIS project and its spatial data for field data collection using **QField** — a mobile GIS application. It creates self-contained project packages trimmed physically to selected administrative/enumeration boundaries (EA or Barangay Level) that can be deployed on Android and iOS devices for offline fieldwork.

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
- Configuring layer roles, QField editing permissions (writable vs read-only), and custom export file formats (`.geojson`, `.gpkg`, `.shp`, `data.gpkg`).

---

## Key Features

### 1. Interactive Layer Groups & Styles Manager
The Package Dialog features a dynamic **Layer Groups & Styles** panel allowing complete customization of layer hierarchy, group ordering, role assignments, and QML symbology styles.

- **Multi-Selection (`Shift` / `Ctrl`)**: Select multiple layers or groups at once:
  - `Shift + Click`: Select a contiguous range of layers or groups.
  - `Ctrl + Click`: Multi-select individual non-adjacent layers or groups.
- **Drag-and-Drop Grouping**: Click and drag single or multi-selected layers into any custom group folder.
- **Keyboard Reordering (`Alt` + Arrow Keys)**:
  - `Alt + Up`: Move selected item(s) **UP**.
  - `Alt + Down`: Move selected item(s) **DOWN**.
  - `Alt + Left`: Move selected item(s) **OUT** to parent level.
  - `Alt + Right`: Move selected item(s) **IN** into preceding group.
- **QML Style Auto-Detection & Application**: Automatically matches layer names to built-in `.qml` style files (e.g., `1. Base Layer Building Points.qml`, `5. Base Layer Barangay.qml`, `Form2_2026_v5.qml`).

---

### 2. Group Layout Presets
- **Built-in Presets**:
  - `Form 2 Layout`: Automatically creates standard `Geotagged Building Point`, `Reference Building Point`, and `Base Layers` group folders.
  - `Form 8 Layout`: Automatically creates standard `Verification Layers` and `Base Layers` group folders.
- **Custom User Presets**:
  - **`💾 Save`**: Save custom group folder structures for quick re-use across projects.
  - **`📂 Load`**: Instantly load built-in or user-saved group layouts and drag-and-drop project layers into them.
  - **`🗑 Delete Preset`**: Delete custom user presets.

---

### 3. Decoupled Role Properties & Policy Manager (`⚙ Configuration`)
Configure QField policies per **Assigned Role** under **⚙ Configuration → Layer Properties**:

- **QField Action**: Choose `Offline Editing` (Writable) vs `Copy / Read-Only` (Background Reference).
- **Identifiable**: Toggle feature identification visibility in QField (`✓`).
- **Read-Only**: Lock or unlock editing per layer role (`✓`).
- **Searchable**: Toggle feature searchability in the QField search bar (`✓`).
- **Export Format**: Select package container/file format per role:
  - `(data.gpkg)`: Combined GeoPackage dataset for reference layers.
  - `.geojson`: Standalone GeoJSON file format.
  - `.gpkg`: Standalone GeoPackage file.
  - `.shp`: Standalone ESRI Shapefile dataset.

#### Assigned Role Suffix & Naming Rules

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

---

### 4. Physical Feature Trimming & EA Geocode Resolution
- **Physical Trimming**: During export, vector layers are physically trimmed to contain **ONLY the features matching the target EA or Barangay**. Out-of-area features are excluded, yielding lightweight, fast-loading files for mobile devices.
- **`ea_geocode` Field Prioritization**: For EA Level exports, the tool prioritizes `ea_geocode` first (before falling back to `geocode`), populating the selection tree with 14-digit EA codes (`04920005001000`).

---

### 5. QField Custom Properties Metadata
Packaged project layers include QGIS `<customproperties>` metadata that instruct QField and QFieldSync on device behavior and synchronization:

- **`QFieldSync/action`** (`offline`, `copy`, `no_action`): Sets offline editing vs background read-only mode in QField.
- **`remoteSource`** & **`remoteLayerId`**: Stores the original desktop master file path so QFieldSync can merge field edits back into master databases.
- **`QFieldSync/sourceDataPrimaryKeys`** (`fid`): Identifies primary key attributes for feature matching.
- **`QFieldSync/photo_naming`**: Manages naming rules for geotagged photos taken in QField.

---

## How to Use

1. Open your QGIS project with all required vector and raster layers.
2. Launch the tool via **GeMa → QField → Package for QField** (`Ctrl+Alt+Q`).
3. In the **Layer Groups & Styles** panel:
   - Click **`📂 Load`** to apply a standard preset (e.g. `Form 2 Layout` or `Form 8 Layout`) or **`➕ Add Group`** for custom groupings.
   - Use `Shift` / `Ctrl` to multi-select layers and drag-and-drop them into target group folders.
   - Use `Alt + Up/Down/Left/Right` keys for rapid keyboard reordering.
   - Assign layer roles (`Geotagging Layer`, `Building points`, `EA layer`, etc.).
4. Click **▶ Apply Groups & Styles** to apply group ordering and QML symbology to your active QGIS project.
5. (Optional) Open **⚙ Configuration** to set per-role **Export Formats** (`.geojson`, `.gpkg`, `.shp`, `(data.gpkg)`) and editing permissions.
6. Select your output level (**EA Level** or **Barangay Level**) and select target area(s) from the **Select City/Municipality Tree**.
7. Click **Package** (or **Batch Export**) to generate self-contained QField projects in the export folder.
8. Transfer the exported folder to your mobile device and open in QField.

---

## Requirements

- Saved QGIS project (`.qgs` or `.qgz`)
- bundled `libqfieldsync` library (included with GeMa Plugin)
- GDAL tools accessible via PyQGIS environment

::: tip
Always verify your packaged project on a test device before deploying to field enumerators. Ensure all layers load properly and offline editing forms function as intended.
:::
