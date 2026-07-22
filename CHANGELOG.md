# Changelog

All notable changes to the **GEMMA** (GIS Extension for Map Management and Analysis) QGIS plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] - 2026

### Highlights
- Added LGU CRS and Geometry Alignment Algorithm to Processing Provider
- Removed unnecessary subfolder and added README for better documentation
- Introduced QP Generation and Create Enumeration Areas QGIS Plugin
- Registered EA Delineation processing provider with UI actions and interactive candidate preview
- Improved Package Dialog functionality by resolving bugs
- Harmonized legacy plugin references and introduced default presets for user convenience
- Updated GEMMA repository URLs and renamed GMD Pipeline to GEMMA
- Implemented GitHub Actions workflow for automated plugin releases and notifications
- Initialized documentation site with tool guides and enhanced README for clarity

## [3.0.0] - 2026

### Added
- **VitePress Documentation Site**: Published interactive documentation hosted via GitHub Pages with full user guide, tool documentation, and getting started instructions.
- **Geometry Repair Toolkit**: Integrated automated geometry validation and repair tool (detect duplicate geometries, null geometries, invalid shapes, wrong feature types with auto-fix).
- **CI/CD Workflows**: Added GitHub Actions workflows for automated plugin packaging & release (`release-plugin.yml`) and documentation site deployment (`deploy-docs.yml`).

### Changed
- Improved overall performance and stability of processing algorithms and UI widgets.
- Renamed release workflow from QGIS Plugin to GEMMA Plugin.
- Harmonized branding and nomenclature to GEMMA across all UI elements and documentation.

## [2.0.0]

### Added
- **Create Enumeration Areas**: Added EA delineation capabilities for census and survey field operations.
- **Package for QField Enhancements**: Improved package dialog with drag-and-drop layer management for QField exports.
- **Interactive EA Preview Widget**: Interactive map preview for candidate enumeration area polygons.
- **GitHub Templates**: Added issue templates for bug reports and feature requests.

### Changed
- Registered EA Delineation processing provider with new UI actions.
- Introduced default presets for enhanced user experience.
- Removed unnecessary cache files to streamline plugin performance.
- Updated repository URLs and documentation links.

## [1.2.0]

### Added
- **Fill Polygon Gaps**: Automatically fill gaps between polygon boundaries.
- **Update Metadata**: Auto-populate LGU PSGC metadata using reference lookup tables.
- **Fix LGU CRS / Geometry**: Reposition and rescale LGU boundary layers to standard EPSG:4326.

## [1.1.0]

### Added
- Integrated **Package for QField** tool from `qfieldmod` plugin.

## [1.0.0]

### Added
- Initial release featuring the **MBI Checker** (Gaps and Overlaps Checker).
