# Changelog

All notable changes to the **GEMMA** (GIS Extension for Map Management and Analysis) QGIS plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.6] - 2026-08-20

### Changed
- Enhanced changelog link generation to ensure accurate references ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Fixed
- Corrected HuggingFace Inference API endpoints to resolve connectivity issues ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#143](https://github.com/GMD-Repository/gemma-plugin/pull/143))

## [1.0.5] - 2026-08-20

### Fixed
- Fixed HuggingFace Inference API endpoints and improved the model fallback chain  (#142) ([@kentemman-gmd](https://github.com/kentemman-gmd))

## [1.0.4] - 2026-08-20

### Added
- Implemented MBI validator tool, enhancing data validation capabilities (@psacjperez) (#139)

### Changed
- Added support for duplicate vertices fix in geometry repair toolkit (@psacjperez)
- Modified update metadata and joined barangay attributes for improved data handling (@psacjperez) (#139)
- Supported 'len' and 'length' keyword arguments in QgsField mock for better compatibility (@psacjperez) (#139)

### Fixed
- Fixed HuggingFace Inference API endpoints and model fallback chain to ensure stable performance (@kentemman-gmd) (#141)

### Documentation
- Added project documentation and utilities for geometry and attribute processing (@psacjperez) (#139)

## [1.0.3] - 2026-08-20

### Added
- Modularize EA creation pipeline, refine processing UI, and add user documentation ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#127](https://github.com/GMD-Repository/gemma-plugin/pull/127))
- Implement Create Enumeration Areas algorithm and automated QGIS testing pipeline ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#131](https://github.com/GMD-Repository/gemma-plugin/pull/131))
- Add EA processing, geometry cleaning, and delineation tools ([@pacoleslaw](https://github.com/pacoleslaw)) ([#134](https://github.com/GMD-Repository/gemma-plugin/pull/134))
- implement Auto Arrange tool with QML styling, single-symbol gap/overlap rendering, and PSGC grouping ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#136](https://github.com/GMD-Repository/gemma-plugin/pull/136))
- add dependency_checker to automatically install and update required QGIS plugins ([@nbacquiano-ui](https://github.com/nbacquiano-ui))
- implement custom QGIS dialog and processing algorithm for creating enumeration areas ([@kentemman-gmd](https://github.com/kentemman-gmd))
- add custom QGIS dialog for Create Enumeration Areas processing algorithm ([@kentemman-gmd](https://github.com/kentemman-gmd))
- add Custom Processing UI dialog and helper class for EA delineation workflow management ([@kentemman-gmd](https://github.com/kentemman-gmd))
- implement EA creation pipeline including delineation, merge, and output phases ([@kentemman-gmd](https://github.com/kentemman-gmd))
- add EA creation tool logic, spatial helpers, and user guide documentation ([@kentemman-gmd](https://github.com/kentemman-gmd))
- add documentation for Create Enumeration Areas tool ([@kentemman-gmd](https://github.com/kentemman-gmd))
- implement automated stable release pipeline with changelog generation and email notifications ([@kentemman-gmd](https://github.com/kentemman-gmd))
- implement robust dependency verification and conditional updates in plugin initialization ([@nlb-sketch](https://github.com/nlb-sketch))
- implement comprehensive unit testing suite, CI pipeline, and mock infrastructure for plugin modules ([@kentemman-gmd](https://github.com/kentemman-gmd))
- implement comprehensive unit test suite and QGIS environment mocks for plugin modules ([@kentemman-gmd](https://github.com/kentemman-gmd))
- implement Check and Update tool with navigation, documentation, and geocode metadata support ([@velascojasper0](https://github.com/velascojasper0))

### Changed
- streamline LGU geocode metadata export, topology validation, and auto-numbered GPKG saving ([@velascojasper0](https://github.com/velascojasper0)) ([#125](https://github.com/GMD-Repository/gemma-plugin/pull/125))
- Robust Dependency Verification & Conditional Updates in Plugin Initialization ([@nbacquiano-ui](https://github.com/nbacquiano-ui)) ([#124](https://github.com/GMD-Repository/gemma-plugin/pull/124))
- Align Gemma Release bot identity in preview release workflow ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#138](https://github.com/GMD-Repository/gemma-plugin/pull/138))
- render professional categorized release body with emoji section headers ([@kentemman-gmd](https://github.com/kentemman-gmd))
- remove unused module and its associated files ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Fixed
- extract legacy geometry check tool, replace Tab 2 with repair toolkit, and remove metadata placeholder ([@velascojasper0](https://github.com/velascojasper0)) ([#132](https://github.com/GMD-Repository/gemma-plugin/pull/132))

### Documentation
- replace discontinued GitHub Models AI changelog with rule-based categorizer ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#121](https://github.com/GMD-Repository/gemma-plugin/pull/121))
- /changelog ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#130](https://github.com/GMD-Repository/gemma-plugin/pull/130))
- replace discontinued GitHub Models AI changelog with rule-based categorizer ([@kentemman-gmd](https://github.com/kentemman-gmd))

## [1.0.2] - 2026-08-07

### Added
- enhance Pre-Processing digitizing workflow & Topology Checker automation ([@velascojasper0](https://github.com/velascojasper0)) ([#120](https://github.com/GMD-Repository/gemma-plugin/pull/120))
- add digitize dock widget, single feature edit guard, and snapping options ([@velascojasper0](https://github.com/velascojasper0)) ([#122](https://github.com/GMD-Repository/gemma-plugin/pull/122))
- implement Check and Update tool for boundary georeferencing, geometry repair, and metadata updates ([@velascojasper0](https://github.com/velascojasper0))
- add digitize dock widget, single feature edit guard, and snapping options ([@velascojasper0](https://github.com/velascojasper0))

## [1.0.1] - 2026-08-05

### Added
- implement automated stable release pipeline ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#117](https://github.com/GMD-Repository/gemma-plugin/pull/117))
- ed Pipeline override ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#118](https://github.com/GMD-Repository/gemma-plugin/pull/118))
- implement automated stable release pipeline with email notifications and version management scripts ([@kentemman-gmd](https://github.com/kentemman-gmd))
- add stable release workflow and VitePress configuration utility script ([@kentemman-gmd](https://github.com/kentemman-gmd))

## [1.0.0] - 2026-07-22

### Added
- **MBI Checker**: Gaps and Overlaps Checker for boundary polygon integrity validation ([@kentemman-gmd](https://github.com/kentemman-gmd), [@pacoleslaw](https://github.com/pacoleslaw), [@velascojasper0](https://github.com/velascojasper0))
- **Create Enumeration Areas & QP Generation**: Automated EA delineation and Quick Plan generation ([@velascojasper0](https://github.com/velascojasper0), [@kentemman-gmd](https://github.com/kentemman-gmd))
- **Fix LGU CRS & Geometry**: Coordinate reference system alignment algorithm and geometry repair tools ([@velascojasper0](https://github.com/velascojasper0), [@kentemman-gmd](https://github.com/kentemman-gmd))
- **Fill Polygon Gaps**: Automatic gap identification and filling for polygon layers ([@pacoleslaw](https://github.com/pacoleslaw), [@kentemman-gmd](https://github.com/kentemman-gmd))
- **Geometry Repair Toolkit**: Comprehensive toolkit for fixing invalid geometries and topological errors ([@kentemman-gmd](https://github.com/kentemman-gmd), [@velascojasper0](https://github.com/velascojasper0))
- **Export Preliminary Polygons**: Export tools for field survey preliminary polygon data ([@pacoleslaw](https://github.com/pacoleslaw), [@kentemman-gmd](https://github.com/kentemman-gmd))
- **Package for QField**: Packaging dialog and tools for offline mobile GIS workflows in QField ([@velascojasper0](https://github.com/velascojasper0), [@kentemman-gmd](https://github.com/kentemman-gmd))
- **Join Barangay Attributes**: Advanced fuzzy matching algorithm for joining administrative attributes ([@psacjperez](https://github.com/psacjperez), [@kentemman-gmd](https://github.com/kentemman-gmd))

### Changed & Improved
- Improved Package Dialog functionality and introduced default presets for user convenience ([@velascojasper0](https://github.com/velascojasper0), [@kentemman-gmd](https://github.com/kentemman-gmd))
- Enhanced drag-and-drop support for improved user experience ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Harmonized legacy plugin references and updated repository metadata ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Infrastructure & Documentation
- Initialized VitePress documentation site with comprehensive user guides and tool documentation ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Implemented automated GitHub Actions workflows for plugin packaging, release management, and preview builds ([@kentemman-gmd](https://github.com/kentemman-gmd))
