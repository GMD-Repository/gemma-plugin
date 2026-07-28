# Changelog

All notable changes to the **GEMMA** (GIS Extension for Map Management and Analysis) QGIS plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.13] - 2026-07-28

### Added
- Added automated GitHub Actions workflows for both preview and stable plugin releases ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Implemented automated release pipeline with email notifications and changelog generation ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Changed
- Improved plugin unload logic by safely removing UI elements and handling processing provider cleanup ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Simplified unload logic and cleanup processing provider removal in gmd_pipeline.py ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Fixed
- Added safe dialog closure and robust processing provider removal to prevent QGIS crashes on plugin unload ([@kentemman-gmd](https://github.com/kentemman-gmd))

## [1.0.12] - 2026-07-28

### Added
- Added a script to collect and clean GitHub PRs and commits for automated changelog generation ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Added a system prompt for automated release notes generation ([@kentemman-gmd](https://github.com/kentemman-gmd))

## [1.0.11] - 2026-07-28

### Added
- Added comprehensive user guide documentation for GEMMA plugin tools and initialization
- Added Contributors component to display repository contributors in documentation
- Added custom branding styles for VitePress documentation

### Changed
- Enhanced and updated changelogs for better clarity
- Implemented documentation generation system for streamlined updates
- Improved automated release creation and documentation update scripts for the GEMMA pipeline

## [1.0.10] - 2026-07-27

### Added
- Added a Getting Started guide to assist new users in utilizing the GEMMA Plugin ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Changed
- Updated beta channel files for preview versions r287 and r289 to ensure compatibility ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Documentation
- Updated documentation generator skill definition for better clarity ([@kentemman-gmd](https://github.com/kentemman-gmd))

## [1.0.9] - 2026-07-27

### Added
- Added GitHub Actions workflow to automate stable plugin releases and notifications ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Changed
- Updated beta channel files for preview version r283

## [1.0.8] - 2026-07-27

### Added
- Added GitHub Actions workflow for automating stable plugin releases and email notifications ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Changed
- Updated beta channel files for preview r276 and r279

## [1.0.7] - 2026-07-27

### Added
- Added automated release workflow for stable plugin builds with email notifications ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Changed
- Updated beta channel files for preview version r272

## [1.0.6] - 2026-07-27

### Added
- Added interactive TablePreviewWidgetWrapper for visualizing enumeration area delineation and merging ([@kentemman-gmd](https://github.com/kentemman-gmd), [@velascojasper0](https://github.com/velascojasper0))

### Changed
- Updated PyQGIS processing scripts and tool icons for improved performance and usability ([@kentemman-gmd](https://github.com/kentemman-gmd), [@velascojasper0](https://github.com/velascojasper0))
- Updated user guide documentation for better clarity and guidance ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Documentation
- Updated user guide to reflect recent changes and enhancements ([@kentemman-gmd](https://github.com/kentemman-gmd))

## [1.0.5] - 2026-07-27

### Added
- Added new skills for enhanced functionality in GIS processing ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Implemented EA delineation algorithm for improved boundary analysis ([@velascojasper0](https://github.com/velascojasper0))
- Added QGISRepositoryCard component for easy plugin repository URL copying ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Changed
- Rebranded submenu to Gemma and fixed QML style application in QField packaging ([@velascojasper0](https://github.com/velascojasper0), [@kentemman-gmd](https://github.com/kentemman-gmd))
- Improved automated documentation and release metadata generation pipeline ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Updated beta channel files for previews r257, r260, and r262

### Fixed
- Removed emojis from README section headers for a cleaner presentation ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Fixed issues by removing deprecated utility functions and unused configuration files ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Documentation
- Added reference documentation for PyQGIS architecture, coding standards, and basic usage ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Registered the new qgis-pyscript skill in skills-lock.json ([@kentemman-gmd](https://github.com/kentemman-gmd))

## [1.0.4] - 2026-07-24

### Added
- Added functionality to update index.md download link with the latest version ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Changed
- Updated beta channel files for multiple preview releases to ensure latest features are available

### Fixed
- Corrected regex escape sequence in update_index_md.py for better functionality ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Fixed regex pattern to match index.md YAML format accurately ([@kentemman-gmd](https://github.com/kentemman-gmd))

## [1.0.3] - 2026-07-24

### Added
- Added function to update index.md download link with the latest version ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Changed
- Updated Vitepress navbar version during releases for better user navigation ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Fixed
- Updated beta channel files for previews r234, r236, and r238

## [1.0.2] - 2026-07-24

### Added
- Added interactive preview widget for enumeration area candidate selection in the delineation algorithm ([@velascojasper0](https://github.com/velascojasper0), [@kentemman-gmd](https://github.com/kentemman-gmd))
- Implemented enumeration area delineation algorithm with interactive preview UI ([@velascojasper0](https://github.com/velascojasper0))
- Added dynamic QTabWidget preview for enumeration area delineation and merging ([@velascojasper0](https://github.com/velascojasper0), [@kentemman-gmd](https://github.com/kentemman-gmd))

### Changed
- Improved user interface responsiveness across various components ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Updated icons and fixed LGU CRS issues for better usability ([@velascojasper0](https://github.com/velascojasper0), [@kentemman-gmd](https://github.com/kentemman-gmd))
- Refactored delineation process to a single-pass execution for efficiency ([@velascojasper0](https://github.com/velascojasper0))

### Fixed
- Fixed UNIQUE constraint bugs related to feature IDs in enumeration area processing ([@velascojasper0](https://github.com/velascojasper0))
- Removed redundant greeting from README for clarity ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Documentation
- Updated developer documentation to include new enumeration area delineation features ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Enhanced README to reflect recent updates and improvements ([@kentemman-gmd](https://github.com/kentemman-gmd))

## [1.0.1] - 2026-07-23

### Added
- Implemented automated release pipeline for QGIS plugin packaging and management utilities ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Added release preview workflow badge to README for better visibility ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Changed
- Updated README to reflect new workflows and corrected badge paths ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Overhauled contributing guide to clarify fork-based and team-member workflows ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Updated beta channel files for multiple preview releases to ensure accuracy

### Fixed
- Corrected workflow badge paths and labels in README.md ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Removed redundant local documentation sections in favor of the external documentation site ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Documentation
- Updated documentation tracking system to streamline release processes ([@kentemman-gmd](https://github.com/kentemman-gmd))

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
