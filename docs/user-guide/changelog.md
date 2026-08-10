# Changelog

Changelogs of all GEMMA Plugin stable releases, which are also available [on GitHub](https://github.com/GMD-Repository/gemma-plugin/releases).

## 1.0.2
<time>Aug 07, 2026</time>

### ✨ New Features
- enhance Pre-Processing digitizing workflow & Topology Checker automation ([@velascojasper0](https://github.com/velascojasper0)) ([#120](https://github.com/GMD-Repository/gemma-plugin/pull/120))
- add digitize dock widget, single feature edit guard, and snapping options ([@velascojasper0](https://github.com/velascojasper0)) ([#122](https://github.com/GMD-Repository/gemma-plugin/pull/122))
- implement Check and Update tool for boundary georeferencing, geometry repair, and metadata updates ([@velascojasper0](https://github.com/velascojasper0))
- add digitize dock widget, single feature edit guard, and snapping options ([@velascojasper0](https://github.com/velascojasper0))

<Contributors :contributors="['velascojasper0']" />

## 1.0.1
<time>Aug 05, 2026</time>

### ✨ New Features
- implement automated stable release pipeline ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#117](https://github.com/GMD-Repository/gemma-plugin/pull/117))
- ed Pipeline override ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#118](https://github.com/GMD-Repository/gemma-plugin/pull/118))
- implement automated stable release pipeline with email notifications and version management scripts ([@kentemman-gmd](https://github.com/kentemman-gmd))
- add stable release workflow and VitePress configuration utility script ([@kentemman-gmd](https://github.com/kentemman-gmd))

<Contributors :contributors="['kentemman-gmd']" />

## 1.0.0
<time>Jul 21, 2026</time>

### ✨ New Features
- **MBI Checker**: Gaps and Overlaps Checker for boundary polygon integrity validation ([@kentemman-gmd](https://github.com/kentemman-gmd), [@pacoleslaw](https://github.com/pacoleslaw), [@velascojasper0](https://github.com/velascojasper0))
- **Create Enumeration Areas & QP Generation**: Automated EA delineation and Quick Plan generation ([@velascojasper0](https://github.com/velascojasper0), [@kentemman-gmd](https://github.com/kentemman-gmd))
- **Fix LGU CRS & Geometry**: Coordinate reference system alignment algorithm and geometry repair tools ([@velascojasper0](https://github.com/velascojasper0), [@kentemman-gmd](https://github.com/kentemman-gmd))
- **Fill Polygon Gaps**: Automatic gap identification and filling for polygon layers ([@pacoleslaw](https://github.com/pacoleslaw), [@kentemman-gmd](https://github.com/kentemman-gmd))
- **Geometry Repair Toolkit**: Comprehensive toolkit for fixing invalid geometries and topological errors ([@kentemman-gmd](https://github.com/kentemman-gmd), [@velascojasper0](https://github.com/velascojasper0))
- **Export Preliminary Polygons**: Export tools for field survey preliminary polygon data ([@pacoleslaw](https://github.com/pacoleslaw), [@kentemman-gmd](https://github.com/kentemman-gmd))
- **Package for QField**: Packaging dialog and tools for offline mobile GIS workflows in QField ([@velascojasper0](https://github.com/velascojasper0), [@kentemman-gmd](https://github.com/kentemman-gmd))
- **Join Barangay Attributes**: Advanced fuzzy matching algorithm for joining administrative attributes ([@psacjperez](https://github.com/psacjperez), [@kentemman-gmd](https://github.com/kentemman-gmd))

### ⚡ Improvements & Fixes
- Improved Package Dialog functionality and introduced default presets for user convenience ([@velascojasper0](https://github.com/velascojasper0), [@kentemman-gmd](https://github.com/kentemman-gmd))
- Enhanced drag-and-drop support for improved user experience ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Harmonized legacy plugin references and updated repository metadata ([@kentemman-gmd](https://github.com/kentemman-gmd))

### 🔧 Infrastructure & Documentation
- Initialized VitePress documentation site with comprehensive user guides and tool documentation ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Implemented automated GitHub Actions workflows for plugin packaging, release management, and preview builds ([@kentemman-gmd](https://github.com/kentemman-gmd))

<Contributors :contributors="['kentemman-gmd', 'velascojasper0', 'pacoleslaw', 'psacjperez']" />
