# Changelog

Changelogs of all GEMMA Plugin stable releases, which are also available [on GitHub](https://github.com/GMD-Repository/gemma-plugin/releases).

## 1.0.1
<time>Sep 01, 2026</time>

### ⚡ Improvements & Fixes
- Implemented automated release management and changelog generation workflow ([@kentemman-gmd](https://github.com/kentemman-gmd))

### 🐛 Bug Fixes
- Resolved duplicate author/PR tags and purged v0.0.0 entries ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#196](https://github.com/GMD-Repository/gemma-plugin/pull/196))

### 💥 Breaking Changes
- Hidden EA Delineation and Merging tool on V1.0.0 ([@velascojasper0](https://github.com/velascojasper0)) ([#195](https://github.com/GMD-Repository/gemma-plugin/pull/195))

<Contributors :contributors="['kentemman-gmd', 'velascojasper0']" />

## 1.0.0
<time>Aug 31, 2026</time>

### ✨ New Features
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

### ⚡ Improvements & Fixes
- Optimized geometry repair, attribute matching, and metadata processing for stability ([@psacjperez](https://github.com/psacjperez)) ([#189](https://github.com/GMD-Repository/gemma-plugin/pull/189))
- Implemented phase 8 for spatial EA sorting, vertex cleanup, and feature output generation ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#192](https://github.com/GMD-Repository/gemma-plugin/pull/192))
- Implemented phase 8 output processing module for feature cleaning and refinement alongside associated test suite and mocks ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#192](https://github.com/GMD-Repository/gemma-plugin/pull/192))
- Implemented phase 8 for output feature generation, geometric cleanup, and EA processing ([@kentemman-gmd](https://github.com/kentemman-gmd)) ([#192](https://github.com/GMD-Repository/gemma-plugin/pull/192))

### 🐛 Bug Fixes
- Fixed inconsistencies related to Building Outside the LGU Boundary ([@ftating19](https://github.com/ftating19)) ([#194](https://github.com/GMD-Repository/gemma-plugin/pull/194))

### 💥 Breaking Changes
- Migrated geom_repair_toolkit to legacy status and introduced new geometry check and repair module ([@velascojasper0](https://github.com/velascojasper0)) ([#190](https://github.com/GMD-Repository/gemma-plugin/pull/190))

### 📚 Documentation
- Initialized VitePress documentation site ([@pacoleslaw](https://github.com/pacoleslaw)) ([#193](https://github.com/GMD-Repository/gemma-plugin/pull/193))

<Contributors :contributors="['pacoleslaw', 'kentemman-gmd', 'psacjperez', 'ftating19', 'velascojasper0']" />


