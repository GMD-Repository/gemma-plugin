# Getting Started

## What is GEMMA?

**GEMMA** stands for **GIS Extension for Map Management and Analysis**. It is a QGIS processing plugin developed by the **Geospatial Management Division (GMD)** of the **Philippine Statistics Authority (PSA)**.

The plugin provides a comprehensive set of GIS tools for map management and analysis activities, including boundary checking, geometry repair, metadata management, and field data collection packaging.

## Requirements

| Requirement | Minimum Version |
|-------------|----------------|
| QGIS        | 3.0 or later   |
| Python      | 3.x (bundled with QGIS) |
| OS          | Windows, macOS, or Linux |

## Installation

### Method 1: QGIS Plugin Repository (Recommended)

Installing via custom repository allows QGIS to automatically detect and notify you of plugin updates:

1. Open **QGIS**.
2. Go to **Plugins → Manage and Install Plugins**.
3. Select the **Settings** tab.
4. Click **Add…** to add a repository.
5. Set Name to `GEMMA Repository` and URL to:
   ```
   https://gmd-repository.github.io/gemma-plugin/gemma.xml
   ```

6. Click **OK**, then click **Reload All Repositories**.
7. Go to the **All** tab, search for **GEMMA**, and click **Install Plugin**.

---

### Method 2: Install from ZIP

1. Download the latest release from the [GitHub Releases page](https://github.com/GMD-Repository/gemma-plugin/releases/latest).
2. Open **QGIS**.
3. Go to **Plugins → Manage and Install Plugins**.
4. Select the **Install from ZIP** tab.
5. Click **Browse** and select the downloaded `gemma-plugin-v*.zip` file.
6. Click **Install Plugin**.

---

## Verify Installation

After installation, verify that everything is working:

1. Check the **GeMa** menu in the menu bar — you should see submenus for **Tools** and **QField**.
2. Open the **Processing Toolbox** (`Ctrl+Alt+T`) and look for the **GMD Pipeline** group — you should see all the tools listed there.
3. The **GeMa Toolbar** should display icons for **Package for QField** and **Create Enumeration Areas**.

## Plugin Structure

The GEMMA plugin organizes its tools into the following categories:

### Processing Toolbox — GMD Pipeline

These tools are accessible from the **QGIS Processing Toolbox** under the **GMD Pipeline** provider:

| Tool | Description |
|------|-------------|
| [MBI Checker](/tools/mbi-checker) | Detect gaps and overlaps in barangay boundaries |
| [Fill Polygon Gaps](/tools/fill-polygon-gaps) | Fill gaps between polygon boundaries |
| [Export Preliminary Polygons](/tools/export-preliminary-polygons) | Merge and export resolved boundary layers |
| [Update LGU PSGC Metadata](/tools/update-metadata) | Auto-populate PSGC metadata fields |
| [Fix LGU CRS](/tools/fix-lgu-crs) | Batch-correct local grid coordinates (~0 to ~100,000) to EPSG:4326 |

### GeMa Menu — Tools

| Tool | Access |
|------|--------|
| [Geometry Repair Toolkit](/tools/geometry-repair-toolkit) | GeMa → Tools → Geometry Repair Toolkit |

### GeMa Menu — QField

| Tool | Access | Shortcut |
|------|--------|----------|
| [Package for QField](/tools/package-qfield) | GeMa → QField → Package for QField | `Ctrl+Alt+Q` |
| [Create Enumeration Areas](/tools/create-enumeration-areas) | GeMa → QField → Create Enumeration Areas | — |

## Updating the Plugin

- **Repository Install**: QGIS automatically checks for updates on launch. Navigate to **Plugins → Manage and Install Plugins → Upgrade All**.
- **ZIP Install**: Download the latest ZIP and re-install via **Install from ZIP** to overwrite the previous version.

## Changelog

For version history and detailed release notes, check our dedicated [Changelog Page](/changelog) or visit [GitHub Releases](https://github.com/GMD-Repository/gemma-plugin/releases).

## Support

For bug reports and feature requests, please use the [GitHub Issues](https://github.com/GMD-Repository/gemma-plugin/issues) page.

For direct support, contact the GMD team at **gmd.support@psa.gov.ph**.
