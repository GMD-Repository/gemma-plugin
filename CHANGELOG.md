# Changelog

All notable changes to the **GEMMA** (GIS Extension for Map Management and Analysis) QGIS plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.0] - 2026-08-28

### Added
- **MBI Checker**: Gaps and Overlaps Checker for boundary polygon integrity validation ([@kentemman-gmd](https://github.com/kentemman-gmd), [@pacoleslaw](https://github.com/pacoleslaw), [@velascojasper0](https://github.com/velascojasper0))
- **Create Enumeration Areas & QP Generation**: Automated EA delineation and Quick Plan generation ([@velascojasper0](https://github.com/velascojasper0), [@kentemman-gmd](https://github.com/kentemman-gmd))
- **Fix LGU CRS & Geometry**: Coordinate reference system alignment algorithm and geometry repair tools ([@velascojasper0](https://github.com/velascojasper0), [@kentemman-gmd](https://github.com/kentemman-gmd))
- **Fill Polygon Gaps**: Automatic gap identification and filling for polygon layers ([@pacoleslaw](https://github.com/pacoleslaw), [@kentemman-gmd](https://github.com/kentemman-gmd))
- **Geometry Repair Toolkit**: Comprehensive toolkit for fixing invalid geometries and topological errors ([@kentemman-gmd](https://github.com/kentemman-gmd), [@velascojasper0](https://github.com/velascojasper0))
- **Export Preliminary Polygons**: Export tools for field survey preliminary polygon data ([@pacoleslaw](https://github.com/pacoleslaw), [@kentemman-gmd](https://github.com/kentemman-gmd))
- **Package for QField**: Packaging dialog and tools for offline mobile GIS workflows in QField ([@velascojasper0](https://github.com/velascojasper0), [@kentemman-gmd](https://github.com/kentemman-gmd))
- **Join Barangay Attributes**: Advanced fuzzy matching algorithm for joining administrative attributes ([@psacjperez](https://github.com/psacjperez), [@kentemman-gmd](https://github.com/kentemman-gmd))
- Implemented MBI validator tool, enhancing data validation capabilities (@psacjperez) (#139)
- Modularize EA creation pipeline, refine processing UI, and add user documentation ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#127](https://github.com/GMD-Repository/gemma-plugin/pull/127))
- Implement Create Enumeration Areas algorithm and automated QGIS testing pipeline ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#131](https://github.com/GMD-Repository/gemma-plugin/pull/131))
- Add EA processing, geometry cleaning, and delineation tools ([@pacoleslaw](https://github.com/pacoleslaw)) ([#134](https://github.com/GMD-Repository/gemma-plugin/pull/134))
- implement Auto Arrange tool with QML styling, single-symbol gap/overlap rendering, and PSGC grouping ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#136](https://github.com/GMD-Repository/gemma-plugin/pull/136))
- enhance Pre-Processing digitizing workflow & Topology Checker automation ([@velascojasper0](https://github.com/velascojasper0)) ([#120](https://github.com/GMD-Repository/gemma-plugin/pull/120))
- add digitize dock widget, single feature edit guard, and snapping options ([@velascojasper0](https://github.com/velascojasper0)) ([#122](https://github.com/GMD-Repository/gemma-plugin/pull/122))
- implement Check and Update tool for boundary georeferencing, geometry repair, and metadata updates ([@velascojasper0](https://github.com/velascojasper0))
- implement automated stable release pipeline ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#117](https://github.com/GMD-Repository/gemma-plugin/pull/117))

### Changed & Improved
- Improved Package Dialog functionality and introduced default presets for user convenience ([@velascojasper0](https://github.com/velascojasper0), [@kentemman-gmd](https://github.com/kentemman-gmd))
- Enhanced drag-and-drop support for improved user experience ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Harmonized legacy plugin references and updated repository metadata ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Enhanced changelog link generation to ensure accurate references ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Added support for duplicate vertices fix in geometry repair toolkit (@psacjperez)
- Modified update metadata and joined barangay attributes for improved data handling (@psacjperez) (#139)
- Supported 'len' and 'length' keyword arguments in QgsField mock for better compatibility (@psacjperez) (#139)
- streamline LGU geocode metadata export, topology validation, and auto-numbered GPKG saving ([@velascojasper0](https://github.com/velascojasper0)) ([#125](https://github.com/GMD-Repository/gemma-plugin/pull/125))

### Fixed
- Corrected HuggingFace Inference API endpoints to resolve connectivity issues ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#143](https://github.com/GMD-Repository/gemma-plugin/pull/143))
- Fixed HuggingFace Inference API endpoints and improved the model fallback chain (#142) ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Fixed HuggingFace Inference API endpoints and model fallback chain to ensure stable performance (@kentemman-gmd) (#141)
- extract legacy geometry check tool, replace Tab 2 with repair toolkit, and remove metadata placeholder ([@velascojasper0](https://github.com/velascojasper0)) ([#132](https://github.com/GMD-Repository/gemma-plugin/pull/132))

### Infrastructure & Documentation
- Initialized VitePress documentation site with comprehensive user guides and tool documentation ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Implemented automated GitHub Actions workflows for plugin packaging, release management, and preview builds ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Added project documentation and utilities for geometry and attribute processing (@psacjperez) (#139)
