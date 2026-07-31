---
layout: home

hero:
  name: "GEMMA"
  text: "GIS Extension for Map Management & Analysis"
  tagline: Standardized & harmonized GIS tools and processing pipeline for GMD activities
  image:
    src: /icons/gemma.svg
    alt: GEMMA Logo
  actions:
    - theme: brand
      text: Get Started
      link: /getting-started
    - theme: alt
      text: Download
      link: https://github.com/GMD-Repository/gemma-plugin/releases/download/v1.0.15/gemma-plugin-v1.0.15.zip

features:
  - icon:
      src: /icons/overlap.svg
    title: MBI Checker
    details: Detect overlaps and gaps between barangay polygon boundaries with building point validation. Supports exporting styled MBI layers as GPKG.
    link: /tools/mbi-checker
    linkText: View Guide
  - icon:
      src: /icons/fill.svg
    title: Fill Polygon Gaps
    details: Automatically fill gaps between polygons by assigning them to the correct neighboring barangay with a preview-before-apply workflow.
    link: /tools/fill-polygon-gaps
    linkText: View Guide
  - icon:
      src: /icons/export.svg
    title: Export Preliminary Polygons
    details: Merge and export resolved barangay boundary layers into a consolidated preliminary output for 1Map submission.
    link: /tools/export-preliminary-polygons
    linkText: View Guide
  - icon:
      src: /icons/update.svg
    title: Update LGU PSGC Metadata
    details: Auto-populate PSGC codes, region, province, and city/municipality fields using a reference table with fuzzy name matching.
    link: /tools/update-metadata
    linkText: View Guide
  - icon:
      src: /icons/crs.svg
    title: Fix LGU CRS
    details: Batch-correct or reposition vector layers digitized in local arbitrary grid coordinates (~0 to ~100,000) to standard WGS 84 (EPSG:4326) using 2D Affine OLS transformation.
    link: /tools/fix-lgu-crs
    linkText: View Guide
  - icon:
      src: /icons/upload.svg
    title: Join Barangay Attributes
    details: Perform enhanced attribute joins between LGU vector layers and PSGC reference tables using fuzzy matching and Roman numeral normalization.
    link: /tools/join-barangay-attributes
    linkText: View Guide
  - icon:
      src: /icons/repair_geom.svg
    title: Geometry Repair Toolkit
    details: Validate and repair polygon geometries — detect duplicates, null geometries, invalid shapes, and wrong-type features with auto-fix capabilities.
    link: /tools/geometry-repair-toolkit
    linkText: View Guide
  - icon:
      src: /icons/scan_errors.svg
    title: Scan Geometry Errors
    details: Scan vector polygon layers for specific geometry and topology defects and generate a Point Vector Sink with audit metadata.
    link: /tools/scan-geometry-errors
    linkText: View Guide
  - icon:
      src: /icons/repair_geom.svg
    title: Repair Polygon Geometries
    details: Reconstruct invalid polygon geometries and recover missing shapes into a clean vector output layer with selection support.
    link: /tools/repair-polygon-geometries
    linkText: View Guide
  - icon:
      src: /icons/check_and_update.svg
    title: Check and Update
    details: Interactive 3-Phase dialog workflow for georeferencing, targeted geometry error scanning/repair, and metadata updating.
    link: /tools/check-and-update
    linkText: View Guide
  - icon:
      src: /icons/packager.svg
    title: Package for QField
    details: Package your QGIS project for field data collection using QField with drag-and-drop layer management.
    link: /tools/package-qfield
    linkText: View Guide
  - icon:
      src: /icons/create_ea.svg
    title: Create Enumeration Areas
    details: Delineate enumeration areas from barangay boundaries for census and survey field operations.
    link: /tools/create-enumeration-areas
    linkText: View Guide
  - icon:
      src: /icons/clip_layers.svg
    title: Clip Project Layers by Extent
    details: Batch clip multiple vector layers to administrative boundary polygons with optional buffer margins.
    link: /tools/clip-project-layers
    linkText: View Guide
---

