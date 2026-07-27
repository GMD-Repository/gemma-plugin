# QGIS Coding & Architecture Standards

This document outlines the strict coding, naming, and structural standards for PyQGIS development.

## 1. PyQGIS Coding Standards

**Always:**
*   Use type hints for function arguments and return types.
*   Use standard Python docstrings for all classes and functions.
*   Use descriptive variable names (e.g., `buffer_distance` instead of `d`).
*   Use structured logging (via the `logging` module) rather than standard `print()` statements in production code.
*   Handle exceptions explicitly (e.g., `try...except QgsProcessingException`).
*   Validate all inputs, assumptions, and CRS compatibility before processing.
*   Use comments only where business logic is complex; prefer self-documenting code.
*   Use simple, professional text for comments.

**Avoid:**
*   Magic values (use constants at the top of the file or class).
*   Silent failures (always log or raise exceptions).
*   Excessive globals.
*   Unnecessary complexity.
*   Emojis in source code (comments, docstrings, log messages).
*   Emojis in UI elements (window titles, labels, buttons, tooltips). Use standard QGIS/Qt icons (`QIcon`) instead.

## 2. Naming Standards

*   **Files / Modules:** Use `snake_case.py` (e.g., `detect_polygon_overlaps.py`, `split_gpkg_by_region.py`). Avoid `MyTool.py` or `ToolV2.py`.
*   **Processing Algorithm IDs:** Use lowercase strings with no spaces or special characters except underscores (e.g., `detect_overlaps`).
*   **Classes:** Use `PascalCase` (e.g., `DetectOverlapsAlgorithm`).
*   **Functions / Variables:** Use `snake_case` (e.g., `calculate_centroid()`).

## 3. Plugin Architecture Standards

Avoid flat architectures for large plugins. Separate UI, Business Logic, Processing, Validation, and Testing into distinct packages.

Use scalable plugin architecture:

```text
plugin_name/
├── __init__.py
├── metadata.txt
├── plugin.py
├── resources.qrc
├── resources.py
├── gui/
│   ├── dialogs/
│   ├── dock_widgets/
│   ├── widgets/
│   └── ui/
├── processing_provider/
│   ├── provider.py
│   └── algorithms/
├── core/
│   ├── services/
│   ├── models/
│   ├── validators/
│   ├── repositories/
│   └── workflows/
├── docs/
└── tests/
```

## 4. Logging Standards

Use structured logging to facilitate debugging.

Levels:
*   **DEBUG**: Detailed information, typically of interest only when diagnosing problems.
*   **INFO**: Confirmation that things are working as expected.
*   **WARNING**: An indication that something unexpected happened, but the software is still working.
*   **ERROR**: Due to a more serious problem, the software has not been able to perform some function.

Do not use random `print()` statements in final plugin or algorithm code. For Processing Algorithms, prefer `QgsProcessingFeedback.pushInfo()` and `QgsProcessingFeedback.reportError()`.

## 5. Documentation Requirements

For substantial implementations, always provide:
*   **Purpose**: What the script/tool solves.
*   **Inputs**: Required layers, types, fields, or parameters.
*   **Outputs**: Expected results or modified layers.
*   **Dependencies**: Required libraries or specific QGIS versions.
*   **Usage Notes**: How a user should interact with the tool.
*   **Limitations**: Known constraints (e.g., "Fails on datasets over 1M features").
*   **Performance Notes**: Threading assumptions or indexing strategies.
