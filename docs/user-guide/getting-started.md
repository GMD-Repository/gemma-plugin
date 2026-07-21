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

### Download

Download the latest release from the [GitHub Releases page](https://github.com/GMD-Repository/gemma-plugin/releases/latest).

Look for the file named `gemma-plugin-v*.zip` under the **Assets** section of the latest release.

### Install via QGIS

1. Open **QGIS**.
2. Go to **Plugins → Manage and Install Plugins**.
3. Select the **Install from ZIP** tab.
4. Click **Browse** and select the downloaded `gemma-plugin-v*.zip` file.
5. Click **Install Plugin**.
6. Once installed, you should see the **GeMa** menu in the QGIS menu bar and the **GeMa Toolbar** with quick access buttons.

### Verify Installation

After installation, verify that everything is working:

1. Check the **GeMa** menu in the menu bar — you should see submenus for **Reports**, **Tools**, and **QField**.
2. Open the **Processing Toolbox** (`Ctrl+Alt+T`) and look for the **GMD Pipeline** group — you should see all the 1Map tools listed there.
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
| [Fix LGU CRS / Geometry](/tools/fix-lgu-crs) | Reproject and reposition LGU layers |

### GeMa Menu — Tools

| Tool | Access |
|------|--------|
| [Geometry Repair Toolkit](/tools/geometry-repair-toolkit) | GeMa → Tools → Geometry Repair Toolkit |

### GeMa Menu — QField

| Tool | Access | Shortcut |
|------|--------|----------|
| [Package for QField](/tools/package-qfield) | GeMa → QField → Package for QField | `Ctrl+Alt+Q` |
| [Create Enumeration Areas](/tools/create-enumeration-areas) | GeMa → QField → Create Enumeration Areas | — |

### GeMa Menu — Reports

| Tool | Access |
|------|--------|
| [Sync MBI Layer](/tools/sync-mbi-layer) | GeMa → Reports → Sync MBI Layer |

## Updating the Plugin

To update to a newer version:

1. Download the latest `.zip` from the [Releases page](https://github.com/GMD-Repository/gemma-plugin/releases/latest).
2. In QGIS, go to **Plugins → Manage and Install Plugins → Install from ZIP**.
3. Install the new `.zip` — it will overwrite the previous version.
4. **Restart QGIS** to ensure all changes take effect.

## Changelog

See the [Releases page](https://github.com/GMD-Repository/gemma-plugin/releases) for a full version history with release notes.

### Version History

| Version | Highlights |
|---------|-----------|
| **3.0.0** | Improved overall functionality and performance; added CI/CD release automation |
| **2.0.0** | Added Create Enumeration Areas; improved QField Package Dialog with drag-and-drop; harmonized plugin naming to GEMMA |
| **1.2.0** | Added Fill Polygon Gaps, Update Metadata, Fix LGU CRS, Create Enumeration Areas |
| **1.1.0** | Integrated Package for QField |
| **1.0.0** | Initial release with Gaps and Overlaps Checker |

## Support

For bug reports and feature requests, please use the [GitHub Issues](https://github.com/GMD-Repository/gemma-plugin/issues) page.

For direct support, contact the GMD team at **gmd.support@psa.gov.ph**.
