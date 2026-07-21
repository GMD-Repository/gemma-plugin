---
layout: home

hero:
  name: "GEMMA Plugin"
  text: "GIS Extension for Map Management and Analysis"
  tagline: A standardized and harmonized pipeline and tools for GMD activities - developed by the Geospatial Management Division of the Philippine Statistics Authority.
  actions:
    - theme: brand
      text: Get Started
      link: /getting-started
    - theme: alt
      text: Download Latest Release
      link: https://github.com/GMD-Repository/gemma-plugin/releases/latest

features:
  - icon:
      src: /icons/overlap.png
    title: MBI Checker
    details: Detect overlaps and gaps between barangay polygon boundaries with building point validation. Supports exporting styled MBI layers as GPKG.
    link: /tools/mbi-checker
    linkText: View Guide
  - icon:
      src: /icons/icon.png
    title: Fill Polygon Gaps
    details: Automatically fill gaps between polygons by assigning them to the correct neighboring barangay with a preview-before-apply workflow.
    link: /tools/fill-polygon-gaps
    linkText: View Guide
  - icon:
      src: /icons/upload.png
    title: Export Preliminary Polygons
    details: Merge and export resolved barangay boundary layers into a consolidated preliminary output for 1Map submission.
    link: /tools/export-preliminary-polygons
    linkText: View Guide
  - icon:
      src: /icons/icon.png
    title: Update LGU PSGC Metadata
    details: Auto-populate PSGC codes, region, province, and city/municipality fields using a reference table with fuzzy name matching.
    link: /tools/update-metadata
    linkText: View Guide
  - icon:
      src: /icons/crs.png
    title: Fix LGU CRS / Geometry
    details: Reposition and rescale an LGU boundary layer to match a reference layer's coordinate system, outputting in EPSG:4326.
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
  - icon:
      src: /icons/reports.png
    title: Sync MBI Layer
    details: Synchronize MBI reporting layers with Google Sheets for centralized tracking and monitoring.
    link: /tools/sync-mbi-layer
    linkText: View Guide
---

