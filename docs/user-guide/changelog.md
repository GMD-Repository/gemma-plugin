# Changelog

Changelogs of all GEMMA Plugin stable releases, which are also available [on GitHub](https://github.com/GMD-Repository/gemma-plugin/releases).

## 1.0.1
<time>Jul 23, 2026</time>

### ✨ New Features
- Implemented automated release pipeline for QGIS plugin packaging and management utilities
- Added release preview workflow badge to README for better visibility

### ⚡ Improvements & Fixes
- Updated README to reflect new workflows and corrected badge paths
- Overhauled contributing guide to clarify fork-based and team-member workflows
- Updated beta channel files for multiple preview releases to ensure accuracy

### 🐛 Bug Fixes
- Corrected workflow badge paths and labels in README.md
- Removed redundant local documentation sections in favor of the external documentation site

### 📚 Documentation
- Updated documentation tracking system to streamline release processes

<Contributors :contributors="['kentemman-gmd', 'velascojasper0', 'psacjperez']" />

## 1.0.0
<time>Jul 21, 2026</time>

### ✨ New Features
- **MBI Checker**: Gaps and Overlaps Checker for boundary polygon integrity validation.
- **Create Enumeration Areas & QP Generation**: Automated EA delineation and Quick Plan generation.
- **Fix LGU CRS & Geometry**: Coordinate reference system alignment algorithm and geometry repair tools.
- **Fill Polygon Gaps**: Automatic gap identification and filling for polygon layers.
- **Geometry Repair Toolkit**: Comprehensive toolkit for fixing invalid geometries and topological errors.
- **Export Preliminary Polygons**: Export tools for field survey preliminary polygon data.
- **Package for QField**: Packaging dialog and tools for offline mobile GIS workflows in QField.
- **Join Barangay Attributes**: Advanced fuzzy matching algorithm for joining administrative attributes.

### ⚡ Improvements & Fixes
- Improved Package Dialog functionality and introduced default presets for user convenience.
- Enhanced drag-and-drop support for improved user experience.
- Harmonized legacy plugin references and updated repository metadata.

### 🔧 Infrastructure & Documentation
- Initialized VitePress documentation site with comprehensive user guides and tool documentation.
- Implemented automated GitHub Actions workflows for plugin packaging, release management, and preview builds.

<Contributors :contributors="['kentemman-gmd', 'velascojasper0', 'psacjperez', 'tatsmenot', 'pacoleslaw', 'nbacquiano-ui']" />

