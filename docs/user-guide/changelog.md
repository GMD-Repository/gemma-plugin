# Changelog

All notable changes to the **GEMMA** (GIS Extension for Map Management and Analysis) QGIS plugin are documented here.

For detailed release assets, visit the [GitHub Releases](https://github.com/GMD-Repository/gemma-plugin/releases) page.

## [3.0.0] - 2026

### Added
- **VitePress Documentation Site**: Published interactive documentation site with comprehensive user guides and tool reference pages.
- **Geometry Repair Toolkit**: Integrated automated geometry validation and repair tool (detect duplicate geometries, null geometries, invalid shapes, wrong feature types with auto-fix).
- **CI/CD Automation**: Added GitHub Actions workflows for automated plugin ZIP packaging & release and documentation site deployment.

### Changed
- Improved overall performance and stability of processing algorithms and UI widgets.
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
