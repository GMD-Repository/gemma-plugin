# Create Enumeration Areas

The **Create Enumeration Areas** tool provides a dialog for delineating enumeration areas (EAs) from barangay boundaries. EAs are used in census and survey operations to divide barangays into manageable field assignment areas.

## Access

- **Menu:** GeMa → QField → Create Enumeration Areas
- **Toolbar:** GeMa Toolbar → Create Enumeration Areas icon

## When to Use

Use this tool when:

- Preparing enumeration area boundaries for census field operations
- Dividing barangays into smaller areas for survey team assignments
- Creating EA delineation maps for field supervisors

## Features

### EA Delineation Dialog
The tool opens a dedicated dialog (EA Launcher) that provides:

- An interactive interface for creating and editing EA boundaries
- Support for EA candidate preview
- Integration with the EA Delineation processing provider

### Processing Provider
The tool also registers an **EA Delineation** processing provider in QGIS, which provides additional EA-related algorithms accessible from the Processing Toolbox.

## How to Use

1. Load your barangay boundary layers in QGIS
2. Launch the tool via **GeMa → QField → Create Enumeration Areas** or the toolbar icon
3. In the EA Launcher Dialog:
   - Select the barangay layer to delineate
   - Use the interactive tools to create EA boundaries
   - Preview the EA candidates
4. Save the delineated enumeration areas

::: tip
Enumeration areas should be designed to have roughly equal workload in terms of number of households or geographic coverage. Consider terrain, road access, and population density when drawing EA boundaries.
:::
