<h1 align="center">GEMMA - GIS Extension for Map Management and Analysis</h1>

<p align="center">
  <a href="https://github.com/GMD-Repository/gemma-plugin/actions/workflows/release-stable.yml"><img src="https://github.com/GMD-Repository/gemma-plugin/actions/workflows/release-stable.yml/badge.svg?branch=main" alt="Release GEMMA Plugin"></a>
  <a href="https://github.com/GMD-Repository/gemma-plugin/actions/workflows/release-preview.yml"><img src="https://github.com/GMD-Repository/gemma-plugin/actions/workflows/release-preview.yml/badge.svg?branch=main" alt="Release GEMMA Plugin (Preview)"></a>
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


Hello
---

## 📚 Documentation

For installation guides, tool references, and the changelog, visit the **[GEMMA Documentation Site](https://gmd-repository.github.io/gemma-plugin/)**.

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
