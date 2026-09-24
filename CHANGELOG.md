# Changelog

All notable changes to the **GEMMA** (GIS Extension for Map Management and Analysis) QGIS plugin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.9] - 2026-09-24

### Added
- Added EA delineation line generation, candidate merge guards, dialog refresh, and unmerge workflow ([@pacoleslaw](https://github.com/pacoleslaw)) ([#300](https://github.com/GMD-Repository/gemma-plugin/pull/300))
- Implemented enumeration area creation pipeline phases, dialog, and unit tests ([@pacoleslaw](https://github.com/pacoleslaw))

### Changed
- Replaced in-row preview button with row double-click zoom functionality ([@pacoleslaw](https://github.com/pacoleslaw)) ([#287](https://github.com/GMD-Repository/gemma-plugin/pull/287))
- Enhanced individual merge workflow by filtering extracted buildings based on execution mode ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#285](https://github.com/GMD-Repository/gemma-plugin/pull/285))
- Isolated bundled libqfieldsync into gemma_sync namespace ([@velascojasper0](https://github.com/velascojasper0)) ([#299](https://github.com/GMD-Repository/gemma-plugin/pull/299))
- Enabled GDAL multithreaded raster clipping and removed hardcoded .shp export fallback ([@nbacquiano-ui](https://github.com/nbacquiano-ui)) ([#297](https://github.com/GMD-Repository/gemma-plugin/pull/297))
- Added QGIS style for delineated EA lines and QField package preference and dialog modules ([@nbacquiano-ui](https://github.com/nbacquiano-ui))
- Preserved data source during various operations ([@nbacquiano-ui](https://github.com/nbacquiano-ui))

### Fixed
- Prevented access to deleted C++ layer in pipeline splitting lines cleanup ([@pacoleslaw](https://github.com/pacoleslaw))
- Restored candidate preview and map canvas zoom in candidate tables ([@pacoleslaw](https://github.com/pacoleslaw))
- Kept Contested boundary polygons out of geocode deduplication process ([@ftating19](https://github.com/ftating19)) ([#289](https://github.com/GMD-Repository/gemma-plugin/pull/289))

### Removed
- Removed 255-character cap from remarks/involved_bgys fields ([@ftating19](https://github.com/ftating19)) ([#290](https://github.com/GMD-Repository/gemma-plugin/pull/290))

### Documentation
- Added EA delineation and merging dialog implementation along with user guide documentation ([@pacoleslaw](https://github.com/pacoleslaw))

## [1.0.8] - 2026-09-21

### Added
- Implemented EA split dialog, merge preview threshold gating, and barangay-enclosed sequential numbering ([@pacoleslaw](https://github.com/pacoleslaw)) ([#272](https://github.com/GMD-Repository/gemma-plugin/pull/272))
- Added custom UI dialog and unit tests for EA delineation and merging workflow ([@pacoleslaw](https://github.com/pacoleslaw))
- Added custom processing UI dialog and unit tests for merge preview threshold and individual merge ([@pacoleslaw](https://github.com/pacoleslaw))
- Added SplitEADialog and unit tests for splitting enumeration area polygons ([@pacoleslaw](https://github.com/pacoleslaw))
- Added UI dialog and processing phase modules for enumeration area creation reference ([@pacoleslaw](https://github.com/pacoleslaw))
- Added Phase 1 initialization module, split dialog, and unit tests for enumeration area creation ([@pacoleslaw](https://github.com/pacoleslaw))
- Added enumeration area generation phases, dialog, spatial helpers, and unit tests ([@pacoleslaw](https://github.com/pacoleslaw))

### Changed
- Enhanced QGIS mock environment for CRS, vector layer properties, and iteration ([@pacoleslaw](https://github.com/pacoleslaw))
- Made candidate preview table columns resizable and responsive on small screens ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#283](https://github.com/GMD-Repository/gemma-plugin/pull/283))
- Added in-row preview zoom to feature button in candidate tables ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#281](https://github.com/GMD-Repository/gemma-plugin/pull/281))

### Documentation
- Added EA Delineation and Merging tool interface, preview widget, and user guide ([@kentemman-gmd](https://github.com/kentemman-gmd))

## [1.0.7] - 2026-09-16

### Added
- add EA delineation, unmerge dialog, dynamic preview refresh, and individual merging ([@pacoleslaw](https://github.com/pacoleslaw)) ([#265](https://github.com/GMD-Repository/gemma-plugin/pull/265))
- implement interactive EA merge preview, individual merging, unmerge restoration, and session reconciliation ([@pacoleslaw](https://github.com/pacoleslaw)) ([#266](https://github.com/GMD-Repository/gemma-plugin/pull/266))
- add EA delineation, split, unmerge, merge preview threshold gating, and individual EA merge workflow ([@pacoleslaw](https://github.com/pacoleslaw)) ([#268](https://github.com/GMD-Repository/gemma-plugin/pull/268))
- add enumeration area delineation, split, and unmerge tools along with user documentation and unit tests ([@pacoleslaw](https://github.com/pacoleslaw))
- add EA delineation and merging module with UI dialog, user guide, and unit tests ([@pacoleslaw](https://github.com/pacoleslaw))
- add merge preview threshold gating and individual EA merge functionality with unit tests ([@pacoleslaw](https://github.com/pacoleslaw))
- add QGIS plugin ZIP packaging script and unit tests ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Changed
- exclude tests and development assets from plugin ZIP builds ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#269](https://github.com/GMD-Repository/gemma-plugin/pull/269))

## [1.0.6] - 2026-09-14

### Added
- Updated PSA-LGU Boundary Comparison and Run Analysis Plugin ([@ftating19](https://github.com/ftating19)) ([#263](https://github.com/GMD-Repository/gemma-plugin/pull/263))

### Changed
- Separated building points outside LGU and PSA boundaries ([@psacjperez](https://github.com/psacjperez))

### Fixed
- Key deduplication on geocode and prevented cutting islands off barangays ([@psacjperez](https://github.com/psacjperez))
- Published boundary before exploding multiparts and merged rows by geocode ([@psacjperez](https://github.com/psacjperez))
- Repaired geometries before writing either output ([@psacjperez](https://github.com/psacjperez))
- Optimized progress bar to update once instead of per sub-process ([@psacjperez](https://github.com/psacjperez))

## [1.0.5] - 2026-09-14

### Added
- Added 2026_province_boundary as a 5th packaging role ([@psacjperez](https://github.com/psacjperez))

### Changed
- Reconciled Packaged Layers documentation with the latest development merge ([@psacjperez](https://github.com/psacjperez))

### Fixed
- Resolved LGU/PSA boundary precedence and deduplication before MBI detection ([@ftating19](https://github.com/ftating19)) ([#257](https://github.com/GMD-Repository/gemma-plugin/pull/257))
- Fixed the generation of the 2026_province_boundary layer ([@ftating19](https://github.com/ftating19)) ([#259](https://github.com/GMD-Repository/gemma-plugin/pull/259))
- Output 2026_CITYMUN_boundary instead of ref_CITYMUN_boundary ([@psacjperez](https://github.com/psacjperez))

### Removed
- Eliminated the Packaged Layers group and enforced clean grouping across EA tabs ([@pacoleslaw](https://github.com/pacoleslaw)) ([#258](https://github.com/GMD-Repository/gemma-plugin/pull/258))
- Masked dynamically fetched emails in GitHub Actions logs to enhance security ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#254](https://github.com/GMD-Repository/gemma-plugin/pull/254))

## [1.0.4] - 2026-09-13

### Added
- Implemented EA delineation and merging workflow with an interactive split dialog ([@pacoleslaw](https://github.com/pacoleslaw)) ([#220](https://github.com/GMD-Repository/gemma-plugin/pull/220))

### Changed
- Refined unassigned layer filtering and resolved unzipped libqfieldsync paths ([@nbacquiano-ui](https://github.com/nbacquiano-ui)) ([#213](https://github.com/GMD-Repository/gemma-plugin/pull/213))
- Standardized unassigned layer filtering to geocode and ea_geocode ([@nbacquiano-ui](https://github.com/nbacquiano-ui)) ([#230](https://github.com/GMD-Repository/gemma-plugin/pull/230))
- Streamlined projection finder UI and improved edit session handling ([@psacjperez](https://github.com/psacjperez)) ([#249](https://github.com/GMD-Repository/gemma-plugin/pull/249))

### Fixed
- Removed merge candidates output layer and pruned candidate sinks ([@pacoleslaw](https://github.com/pacoleslaw)) ([#242](https://github.com/GMD-Repository/gemma-plugin/pull/242))

### Documentation
- Integrated reference MBI cases and updated documentation ([@psacjperez](https://github.com/psacjperez)) ([#214](https://github.com/GMD-Repository/gemma-plugin/pull/214))
- Updated Geometry Repair Toolkit user guide and enhanced topology diagnostic documentation ([@psacjperez](https://github.com/psacjperez)) ([#221](https://github.com/GMD-Repository/gemma-plugin/pull/221))

## [1.0.3] - 2026-09-03

### Added
- Implemented EA Delineation and Merging module with a dual-tab UI and included unit tests ([@pacoleslaw](https://github.com/pacoleslaw))

### Fixed
- Removed unresolvable @actions/github require from workflow dispatch steps ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Documentation
- Added PSA-LGU boundary comparison tool documentation and configured VitePress ([@kentemman-gmd](https://github.com/kentemman-gmd))

## [1.0.2] - 2026-09-03

### Added
- Implemented EA delineation, candidates algorithm, and unified multi-tab GUI workflow ([@pacoleslaw](https://github.com/pacoleslaw)) ([#202](https://github.com/GMD-Repository/gemma-plugin/pull/202))
- Added custom GUI dialog, merge processor, and EARF automation for EA delineation ([@pacoleslaw](https://github.com/pacoleslaw)) ([#201](https://github.com/GMD-Repository/gemma-plugin/pull/201))
- Enabled EA Delineation and Merging tools in the menu and toolbar ([@pacoleslaw](https://github.com/pacoleslaw))
- Added PackageDialog for QGIS-to-QField project export with custom layer group and style management ([@nbacquiano-ui](https://github.com/nbacquiano-ui))

### Changed
- Route stable release notification recipients to BCC ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#200](https://github.com/GMD-Repository/gemma-plugin/pull/200))
- Add GitHub Actions workflows for automated testing, preview releases, and deployment management ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Add GitHub Actions workflow for stable release deployment and email notifications ([@kentemman-gmd](https://github.com/kentemman-gmd))
- Automated stable release workflow with XML configuration generation and email notifications ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Fixed
- Suppress generation of empty 0-feature outputs and prune unused layer groups in Tab 2 ([@pacoleslaw](https://github.com/pacoleslaw)) ([#203](https://github.com/GMD-Repository/gemma-plugin/pull/203))
- Fix cross-platform path normalization in detect_project_from_layer ([@pacoleslaw](https://github.com/pacoleslaw))

### Removed
- Delete gmd_scripts/cbms_mv/mv_2027_hp_4a_longitude__invalid.py ([@velascojasper0](https://github.com/velascojasper0))

### Documentation
- Update EARF writer docstrings and tool guide documentation ([@pacoleslaw](https://github.com/pacoleslaw))
- Add unit tests for rigid fit and alignment models in LGU boundary comparison ([@ftating19](https://github.com/ftating19))

## [1.0.1] - 2026-09-01

### Changed
- Implemented automated release management and changelog generation workflow ([@kentemman-gmd](https://github.com/kentemman-gmd))

### Fixed
- Resolved duplicate author/PR tags and purged v0.0.0 entries ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#196](https://github.com/GMD-Repository/gemma-plugin/pull/196))

### Removed
- Hidden EA Delineation and Merging tool on V1.0.0 ([@velascojasper0](https://github.com/velascojasper0)) ([#195](https://github.com/GMD-Repository/gemma-plugin/pull/195))

## [1.0.0] - 2026-08-31

### Added
- Implemented EA merge processor, EARF Excel writer, and phase 8 output ([@pacoleslaw](https://github.com/pacoleslaw)) ([#192](https://github.com/GMD-Repository/gemma-plugin/pull/192))
- Implemented EA delineation and merging workflow, launcher UI, and EARF generation ([@pacoleslaw](https://github.com/pacoleslaw)) ([#193](https://github.com/GMD-Repository/gemma-plugin/pull/193))
- Implemented Create Enumeration Area UI and modular processing phase scripts ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#193](https://github.com/GMD-Repository/gemma-plugin/pull/193))
- Implemented EA candidate identification and delineation phase logic with supporting test mocks and utilities ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#195](https://github.com/GMD-Repository/gemma-plugin/pull/195))
- Implemented EA output phase with geometric refinement, vertex cleanup, and unit testing infrastructure ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#196](https://github.com/GMD-Repository/gemma-plugin/pull/196))
- Implemented geometric splitting and hybrid Voronoi-road clustering for EA delineation ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#197](https://github.com/GMD-Repository/gemma-plugin/pull/197))
- Implemented geometric EA splitting and voronoi-based clustering logic in phase5_delineate ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#198](https://github.com/GMD-Repository/gemma-plugin/pull/198))
- Implemented EA Delineation tool with dialog interface and algorithm logic ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#199](https://github.com/GMD-Repository/gemma-plugin/pull/199))
- Implemented enumeration area creation pipeline with modular processing phases and documentation ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#200](https://github.com/GMD-Repository/gemma-plugin/pull/200))
- Implemented EADMCandidatesAlgorithm for automated enumeration area delineation and merging pipeline ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#201](https://github.com/GMD-Repository/gemma-plugin/pull/201))
- Implemented Pre-EA processor workflow to automate boundary clipping and gap assignment ([@pacoleslaw](https://github.com/pacoleslaw)) ([#202](https://github.com/GMD-Repository/gemma-plugin/pull/202))
- Added pre-EA processing, geometry cleaning, and output generation modules for Enumeration Area creation ([@pacoleslaw](https://github.com/pacoleslaw)) ([#203](https://github.com/GMD-Repository/gemma-plugin/pull/203))

### Changed
- Optimized geometry repair, attribute matching, and metadata processing for stability ([@psacjperez](https://github.com/psacjperez)) ([#189](https://github.com/GMD-Repository/gemma-plugin/pull/189))
- Implemented phase 8 for spatial EA sorting, vertex cleanup, and feature output generation ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#192](https://github.com/GMD-Repository/gemma-plugin/pull/192))
- Implemented phase 8 output processing module for feature cleaning and refinement alongside associated test suite and mocks ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#192](https://github.com/GMD-Repository/gemma-plugin/pull/192))
- Implemented phase 8 for output feature generation, geometric cleanup, and EA processing ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#192](https://github.com/GMD-Repository/gemma-plugin/pull/192))

### Fixed
- Fixed inconsistencies related to Building Outside the LGU Boundary ([@ftating19](https://github.com/ftating19)) ([#194](https://github.com/GMD-Repository/gemma-plugin/pull/194))

### Removed
- Migrated geom_repair_toolkit to legacy status and introduced new geometry check and repair module ([@velascojasper0](https://github.com/velascojasper0)) ([#190](https://github.com/GMD-Repository/gemma-plugin/pull/190))

### Documentation
- Initialized VitePress documentation site ([@pacoleslaw](https://github.com/pacoleslaw)) ([#193](https://github.com/GMD-Repository/gemma-plugin/pull/193))

