---
layout: home

hero:
  name: "GEMMA"
  text: "GIS Extension for Map Management & Analysis"
  tagline: Standardized & harmonized GIS tools and processing pipeline for GMD activities
  image:
    src: /icons/gemma.png
    alt: GEMMA Logo
  actions:
    - theme: brand
      text: Get Started
      link: /getting-started
    - theme: alt
      text: Download
      link: https://github.com/GMD-Repository/gemma-plugin/releases/download/v3.0.0/gemma-plugin-v3.0.0.zip

features:
  - icon:
      src: /icons/overlap.png
    title: MBI Checker
    details: Detect overlaps and gaps between barangay polygon boundaries with building point validation. Supports exporting styled MBI layers as GPKG.
    link: /tools/mbi-checker
    linkText: View Guide
  - icon:
      src: /icons/fill.png
    title: Fill Polygon Gaps
    details: Automatically fill gaps between polygons by assigning them to the correct neighboring barangay with a preview-before-apply workflow.
    link: /tools/fill-polygon-gaps
    linkText: View Guide
  - icon:
      src: /icons/export.png
    title: Export Preliminary Polygons
    details: Merge and export resolved barangay boundary layers into a consolidated preliminary output for 1Map submission.
    link: /tools/export-preliminary-polygons
    linkText: View Guide
  - icon:
      src: /icons/update.png
    title: Update LGU PSGC Metadata
    details: Auto-populate PSGC codes, region, province, and city/municipality fields using a reference table with fuzzy name matching.
    link: /tools/update-metadata
    linkText: View Guide
  - icon:
      src: /icons/crs.png
    title: Fix LGU CRS
    details: Batch-correct or reposition vector layers digitized in local arbitrary grid coordinates (~0 to ~100,000) to standard WGS 84 (EPSG:4326) using 2D Affine OLS transformation.
    link: /tools/fix-lgu-crs
    linkText: View Guide
  - icon:
      src: /icons/reports.png
    title: Geometry Repair Toolkit
    details: Validate and repair polygon geometries — detect duplicates, null geometries, invalid shapes, and wrong-type features with auto-fix capabilities.
    link: /tools/geometry-repair-toolkit
    linkText: View Guide
  - icon:
      src: /icons/packager.svg
    title: Package for QField
    details: Package your QGIS project for field data collection using QField with drag-and-drop layer management.
    link: /tools/package-qfield
    linkText: View Guide
  - icon:
      src: /icons/create_ea.png
    title: Create Enumeration Areas
    details: Delineate enumeration areas from barangay boundaries for census and survey field operations.
    link: /tools/create-enumeration-areas
    linkText: View Guide
---

