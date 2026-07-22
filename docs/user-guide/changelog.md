# Changelogs

Changelogs of all GEMMA Plugin stable releases, which are also available [on GitHub](https://github.com/GMD-Repository/gemma-plugin/releases).

## 3.0.1 <Badge type="tip" text="Latest" />
<time>Jul 21, 2026</time>

### ✨ New Features
- **VitePress Documentation Site**: Published interactive documentation hosted via GitHub Pages with full user guide, tool documentation, and getting started instructions.
- **CI/CD Documentation Deployment**: Added GitHub Actions workflow (`deploy-docs.yml`) for automated documentation site building and deployment.
- **Project Documentation**: Comprehensive update to project README with tool guides, installation steps, and architecture overview.

<Contributors :contributors="['velascojasper0', 'tatsmenot', 'kentemman-gmd']" />

## 3.0.0
<time>Jul 21, 2026</time>

### ✨ New Features
- **Geometry Repair Toolkit**: Integrated automated geometry validation and repair tool (detect duplicate geometries, null geometries, invalid shapes, wrong feature types with auto-fix).
- **CI/CD Workflows**: Added GitHub Actions release workflow (`release-plugin.yml`) for automated plugin packaging & release ZIP creation.

### ⚙️ Improvements & Changes
- Improved overall performance and stability of processing algorithms and UI widgets.
- Renamed release workflow from QGIS Plugin to GEMMA Plugin.
- Harmonized branding and nomenclature to GEMMA across all UI elements and documentation.

<Contributors :contributors="['nbacquiano-ui', 'kentemman-gmd', 'velascojasper0']" />

## 2.0.0
<time>Jul 21, 2026</time>

### ✨ New Features
- **Create Enumeration Areas**: Added EA delineation capabilities for census and survey field operations.
- **Package for QField Enhancements**: Improved package dialog with drag-and-drop layer management for QField exports.
- **Interactive EA Preview Widget**: Interactive map preview widget for candidate enumeration area polygons.
- **GitHub Templates**: Added issue templates for bug reports and feature requests.

### ⚙️ Changes
- Registered EA Delineation processing provider with new UI actions.
- Introduced default presets for enhanced user experience.
- Removed unnecessary cache files to streamline plugin performance.
- Updated repository URLs and documentation links.

<Contributors :contributors="['kentemman-gmd', 'velascojasper0', 'nbacquiano-ui']" />

## 1.2.0
<time>Jul 02, 2026</time>

### ✨ New Features
- **Fill Polygon Gaps**: Automatically fill gaps between polygon boundaries.
- **Update Metadata**: Auto-populate LGU PSGC metadata using reference lookup tables.
- **Fix LGU CRS / Geometry**: Reposition and rescale LGU boundary layers to standard EPSG:4326.
- **Create Enumeration Areas**: Initial integration of EA delineation processing provider.

<Contributors :contributors="['kentemman-gmd', 'velascojasper0']" />

## 1.1.1
<time>Jul 02, 2026</time>

### ⚙️ Improvements
- Auto-release metadata workflow improvements and bug fixes.

<Contributors :contributors="['kentemman-gmd']" />

## 1.1.0
<time>Jul 02, 2026</time>

### ✨ New Features
- Integrated **Package for QField** tool from `qfieldmod` plugin.

<Contributors :contributors="['velascojasper0']" />

## 1.0.0
<time>Jul 21, 2026</time>

### ✨ New Features
- Initial release featuring the **MBI Checker** (Gaps and Overlaps Checker).

<Contributors :contributors="['kentemman-gmd', 'velascojasper0']" />
