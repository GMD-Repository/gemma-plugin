# Changelog

All notable changes to the **GEMMA** (GIS Extension for Map Management and Analysis) QGIS plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
