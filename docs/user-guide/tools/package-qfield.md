# Package for QField

The **Package for QField** tool packages your QGIS project and its data for field data collection using **QField** — a mobile GIS application. It creates a self-contained project package that can be loaded on Android devices for offline field work.

## Access

- **Menu:** GeMa → QField → Package for QField
- **Toolbar:** GeMa Toolbar → Package for QField icon
- **Shortcut:** `Ctrl+Alt+Q`

## When to Use

Use this tool when:

- Preparing QGIS projects for field data collection using QField
- You need to create offline-capable project packages for mobile devices
- Setting up projects for census enumeration or survey field work

## Features

### Drag-and-Drop Layer Management
The Package Dialog provides an interactive layer management interface where you can:

- Reorder layers for the QField project
- Select which layers to include in the package
- Configure offline editing settings per layer

### Project Packaging
The tool creates a complete QField-compatible project package including:

- The QGIS project file (`.qgs`)
- All referenced data layers
- Styles and symbology
- Print layouts (if any)

## How to Use

1. Open your QGIS project with all the layers you want to include
2. Launch the tool via **GeMa → QField → Package for QField** (or `Ctrl+Alt+Q`)
3. In the Package Dialog:
   - Review the layer list
   - Configure which layers should be available offline
   - Set the output directory
4. Click **Package** to create the QField project
5. Transfer the packaged project to your Android device
6. Open the project in QField

## Requirements

- A saved QGIS project (`.qgs` or `.qgz`)
- All project layers must be accessible (not broken links)
- The `libqfieldsync` library is bundled with the plugin

::: tip
Test your packaged project on a device or emulator before deploying to the field. Make sure all layers render correctly and offline editing works as expected.
:::
