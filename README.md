<h1 align="center">GEMMA - GIS Extension for Map Management and Analysis</h1>

<p align="center">
  <a href="https://github.com/GMD-Repository/gemma-plugin/actions/workflows/release-stable.yml"><img src="https://github.com/GMD-Repository/gemma-plugin/actions/workflows/gemma-plugin.yml/badge.svg?branch=main" alt="Release GEMMA Plugin"></a>
  <a href="https://github.com/GMD-Repository/gemma-plugin/actions/workflows/release-preview.yml"><img src="https://github.com/GMD-Repository/gemma-plugin/actions/workflows/gemma-plugin.yml/badge.svg?branch=main" alt="Release GEMMA Plugin"></a>
  <a href="https://github.com/GMD-Repository/gemma-plugin/actions/workflows/deploy-docs.yml"><img src="https://github.com/GMD-Repository/gemma-plugin/actions/workflows/deploy-docs.yml/badge.svg?branch=main" alt="Deploy Documentation"></a>
  <a href="https://github.com/GMD-Repository/gemma-plugin/releases"><img src="https://img.shields.io/github/downloads/GMD-Repository/gemma-plugin/total" alt="Total Downloads"></a>
  <img src="https://img.shields.io/badge/QGIS-3.0%2B-brightgreen" alt="QGIS Version">
</p>

<h2 align="center">Download</h2>

<p align="center">
  <a href="https://github.com/GMD-Repository/gemma-plugin/releases/latest"><img src="https://img.shields.io/github/v/release/GMD-Repository/gemma-plugin?label=Stable&color=007ec6" alt="Stable Release"></a>
  <a href="https://github.com/GMD-Repository/gemma-plugin-preview/releases"><img src="https://img.shields.io/github/v/release/GMD-Repository/gemma-plugin-preview?include_prereleases&label=Beta&color=38344e" alt="Beta Release"></a>
</p>

**GEMMA** is a QGIS processing plugin developed by the **Geospatial Management Division (GMD)** of the **Philippine Statistics Authority (PSA)**.

It provides a comprehensive set of GIS tools for map management and analysis activities, including boundary checking, geometry repair, metadata management, enumeration area creation, and field data collection packaging.

---

## 📚 Documentation & Changelog

Complete user guides and documentation are available on our [Documentation Site](https://gmd-repository.github.io/gemma-plugin/) or directly in the repository:

- 🚀 [Getting Started Guide](docs/user-guide/getting-started.md)
- 📜 [Changelog](CHANGELOG.md) / [Docs Changelog Page](docs/user-guide/changelog.md)
- 🛠️ **Tool Guides:**
  - 🗺️ [MBI Checker](docs/user-guide/tools/mbi-checker.md) — Detect gaps & overlaps in barangay boundaries with building point validation.
  - 🧩 [Fill Polygon Gaps](docs/user-guide/tools/fill-polygon-gaps.md) — Automatically fill gaps between polygon boundaries.
  - 📤 [Export Preliminary Polygons](docs/user-guide/tools/export-preliminary-polygons.md) — Merge & export resolved boundary layers for 1Map.
  - 🏷️ [Update LGU PSGC Metadata](docs/user-guide/tools/update-metadata.md) — Auto-populate PSGC metadata fields using reference tables.
  - 🌐 [Fix LGU CRS / Geometry](docs/user-guide/tools/fix-lgu-crs.md) — Reposition and rescale LGU boundary layers to EPSG:4326.
  - 🔧 [Geometry Repair Toolkit](docs/user-guide/tools/geometry-repair-toolkit.md) — Detect and repair duplicate, null, or invalid shapes.
  - 📱 [Package for QField](docs/user-guide/tools/package-qfield.md) — Prepare QGIS projects for mobile field collection (`Ctrl+Alt+Q`).
  - 📐 [Create Enumeration Areas](docs/user-guide/tools/create-enumeration-areas.md) — Delineate enumeration areas for census & field operations.

---

## ✨ Features & Tools Overview

### 1Map Processing Tools (Processing Toolbox)
Accessible from the **QGIS Processing Toolbox** under **GMD Pipeline**:

- **MBI Checker**: Detect overlaps and gaps between barangay polygon boundaries with building point validation. Supports exporting styled MBI layers as GPKG.
- **Fill Polygon Gaps**: Automatically fill gaps between neighbor polygons with a preview-before-apply workflow.
- **Export Preliminary Polygons**: Merge and export resolved barangay boundary layers into a consolidated preliminary output for 1Map submission.
- **Update LGU PSGC Metadata**: Auto-populate PSGC codes, region, province, and city/municipality fields using fuzzy name matching.
- **Fix LGU CRS / Geometry**: Reposition and rescale an LGU boundary layer to match a reference layer's coordinate system (EPSG:4326).

### Geometry & Repair Tools (`GeMa → Tools`)
- **Geometry Repair Toolkit**: Validate and repair polygon geometries — detect duplicates, null geometries, invalid shapes, and wrong feature types with auto-fix capabilities.

### Field Operations & Enumeration (`GeMa → QField`)
- **Package for QField** (`Ctrl+Alt+Q`): Package your QGIS project for field data collection using QField with drag-and-drop layer management.
- **Create Enumeration Areas**: Delineate enumeration areas from barangay boundaries for census and survey field operations.

---

## 💻 Requirements

| Requirement | Minimum Version | Notes |
|---|---|---|
| **QGIS** | 3.0 or later | Recommended: 3.28+ LTR |
| **Python** | 3.x | Bundled with QGIS |
| **OS** | Windows, macOS, Linux | Tested on Windows 10/11 |

---

## ⚙️ Installation

1. **Download the latest release**: Go to the [Releases Page](https://github.com/GMD-Repository/gemma-plugin/releases/latest) and download `gemma-plugin-v*.zip`.
2. **Open QGIS**: Go to `Plugins` → `Manage and Install Plugins...`
3. **Install from ZIP**:
   - Select the **Install from ZIP** tab.
   - Browse and select the downloaded `.zip` file.
   - Click **Install Plugin**.
4. **Verify**: You should now see the **GeMa** menu on the QGIS menu bar, the **GMD Pipeline** group in the Processing Toolbox, and the **GeMa Toolbar**.

---

## 🤝 Contributing & Git Workflow Guide

We welcome contributions from everyone! Choose the workflow that matches your role:

| Role | Workflow | Access Level |
|---|---|---|
| **Contributor** (external / community) | Fork → PR | No direct repo access needed |
| **Developer** (GMD team member) | Branch → PR | Push access to the repo |

---

### 🍴 For Contributors (Fork & Pull Request)

If you are **not** a member of the GMD team, follow this fork-based workflow.

#### Step 1: Fork the Repository

1. Go to [github.com/GMD-Repository/gemma-plugin](https://github.com/GMD-Repository/gemma-plugin).
2. Click the **Fork** button (top-right) to create your own copy of the repository under your GitHub account.

#### Step 2: Clone Your Fork

1. Open VS Code.
2. Press `Ctrl + Shift + P` → type **Git: Clone** → hit Enter.
3. Paste **your fork's URL**: `https://github.com/<your-username>/gemma-plugin.git`
4. When prompted to select a folder, navigate to your QGIS plugins directory:
   `C:\Users\Admin\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\`
   and click **Select Repository Location**.
5. Once it finishes downloading, click **Open** when prompted.
   *(Note: VS Code will name the folder `gemma-plugin` by default. If QGIS needs it to be named `gemma_plugin`, you can rename the folder in your File Explorer later).*

#### Step 3: Keep Your Fork Up to Date

Before starting new work, sync your fork with the upstream repository:

1. **Add upstream remote** (one-time setup): Open a terminal in VS Code (`Ctrl + ~`) and run:
   ```bash
   git remote add upstream https://github.com/GMD-Repository/gemma-plugin.git
   ```
2. **Fetch & merge upstream changes**:
   ```bash
   git checkout main
   git fetch upstream
   git merge upstream/main
   git push origin main
   ```

#### Step 4: Create a Feature Branch & Make Changes

1. **Create a branch:** Click on `main` in the bottom-left corner of VS Code → select **+ Create new branch...** → type a descriptive name (e.g., `fix-gap-detection` or `add-export-tool`).
2. Make your changes on this branch.

#### Step 5: Commit & Push to Your Fork

1. Open the **Source Control** panel (branch icon on the left sidebar).
2. Hover over **Changes** and click the **+ (Stage All Changes)** icon.
3. Type a short, descriptive commit message explaining what you changed.
4. Click **Commit**, then click **Publish Branch** (or **Sync Changes**) to push to your fork.

#### Step 6: Create a Pull Request

1. Go to **your fork** on GitHub — you will usually see a green **"Compare & pull request"** button. Click it.
2. Alternatively, go to the original repo's [Pull requests](https://github.com/GMD-Repository/gemma-plugin/pulls) tab → click **New pull request** → click **compare across forks** → select your fork and branch.
3. Make sure: **base repository** = `GMD-Repository/gemma-plugin` · **base** = `main` · **head repository** = `<your-username>/gemma-plugin` · **compare** = your branch.
4. Add a clear title and description explaining what you changed and why.
5. Click **Create pull request**.
6. Wait for a team member to review and approve your PR!

---

### 🔧 For Developers (Branch Workflow)

If you are a **GMD team member** with push access to the repository, use this direct branching workflow.

**IMPORTANT:** Always do your work on a personal branch. Please use your name for your personal branch (e.g., `john-doe`) so that it's easy to identify who the pull request belongs to.

#### Step 1: Get the Code & Create Your Branch

**Option A: New Users (First-time setup via VS Code)**

If you do not have the project on your computer yet:

1. Open VS Code.
2. Press `Ctrl + Shift + P` → type **Git: Clone** → hit Enter.
3. Paste the repository URL: `https://github.com/GMD-Repository/gemma-plugin.git`
4. When prompted to select a folder, navigate to your QGIS plugins directory:
   `C:\Users\Admin\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\`
   and click **Select Repository Location**.
5. Once it finishes downloading, click **Open** when prompted.
   *(Note: VS Code will name the folder `gemma-plugin` by default. If QGIS needs it to be named `gemma_plugin`, you can rename the folder in your File Explorer later).*
6. **Create your branch:** Click on `main` in the bottom-left corner of VS Code → select **+ Create new branch...** → type your name (e.g., `john-doe`).

**Option B: Existing Users (Update your code & Switch Branch)**

If you already have the project open in VS Code:

1. **Switch to main:** Click your current branch name in the bottom-left corner and select `main`.
2. **Pull updates:** Open the **Source Control** panel (branch icon on the left sidebar). Click the **… (Views and More Actions)** menu → go to **Pull, Push** → click **Pull**.
3. **Switch to (or create) your branch:** Click `main` in the bottom-left corner again.
   - If this is your FIRST time, select **+ Create new branch...** and type your name.
   - If you ALREADY have a branch, simply select your branch name from the list.
   *(Note: If you switched to an existing branch, you can update it by opening the Command Palette (`Ctrl + Shift + P`), typing **Git: Merge Branch**, and selecting `main` to merge the new updates into your personal branch.)*

#### Step 2: Work on Your Personal Branch

Now that you are on your personal branch (double-check the bottom-left corner to ensure it shows your name, not `main`), you can safely edit, add, or move files.

*(Tip: If you need to fix your folder structure by moving files from a subfolder into the root folder, you can simply drag and drop them in the VS Code Explorer!)*

#### Step 3: Save and Push Your Changes

1. Open the **Source Control** panel (branch icon on the left sidebar).
2. Hover over **Changes** and click the **+ (Stage All Changes)** icon to stage your files.
3. Type a short, descriptive commit message explaining what you changed.
4. Click **Commit**, then click **Publish Branch** (or **Sync Changes**) to push your updates to GitHub.

#### Step 4: Create a Pull Request (PR)

1. Go to the repository on GitHub: https://github.com/GMD-Repository/gemma-plugin
2. You will usually see a green **"Compare & pull request"** button for your recently pushed branch. Click it.
3. Alternatively, go to the **Pull requests** tab → click **New pull request**. Make sure the base is `main` and the compare branch is your personal branch.
4. Add a clear title and description explaining what you changed and why.
5. Click **Create pull request**.
6. Wait for a team member to review and approve your PR!

---

## 📬 Support & Contact

- **Issues & Feature Requests**: [GitHub Issues](https://github.com/GMD-Repository/gemma-plugin/issues)
- **Email**: gmd.support@psa.gov.ph
- **Organization**: Geospatial Management Division (GMD), Philippine Statistics Authority
