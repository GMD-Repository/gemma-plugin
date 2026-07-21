[![Release QGIS Plugin](https://github.com/GMD-Repository/gemma-plugin/actions/workflows/release-plugin.yml/badge.svg?branch=main)](https://github.com/GMD-Repository/gemma-plugin/actions/workflows/release-plugin.yml)

# Git Workflow Guide

This step-by-step guide explains how to get the code, create your branch, update it, and submit your changes—all using the VS Code interface!

**IMPORTANT:** Always do your work on a personal branch. Please use your name for your personal branch (e.g., `john-doe`) so that it's easy to identify who the pull request belongs to.

---

## Step 1: Get the Code & Create Your Branch

### Option A: New Users (First-time setup via VS Code)
If you do not have the project on your computer yet:

1. Open VS Code.
2. Press `Ctrl + Shift + P` to open the Command Palette.
3. Type **Git: Clone** and hit Enter.
4. Paste the repository URL: `https://github.com/GMD-Repository/gemma-plugin.git`
5. When prompted to select a folder, navigate to your QGIS plugins directory:
   `C:\Users\Admin\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\`
   and click **Select Repository Location**.
6. Once it finishes downloading, click **Open** when prompted.
*(Note: VS Code will name the folder `gemma-plugin` by default. If QGIS needs it to be named `gemma_plugin`, you can rename the folder in your File Explorer later).*
7. **Create your branch:** Click on `main` in the bottom-left corner of the VS Code window. Select **+ Create new branch...** and type your name (e.g., `john-doe`).

### Option B: Existing Users (Update your code & Switch Branch)
If you already have the project open in VS Code:

1. **Switch to main:** Click your current branch name in the bottom-left corner and select `main`.
2. **Pull updates:** Open the **Source Control** panel (the branch icon on the left sidebar). Click the **... (Views and More Actions)** menu at the top right of the panel, go to **Pull, Push**, and click **Pull**.
3. **Switch to (or create) your branch:** Click `main` in the bottom-left corner again. 
   - If this is your FIRST time, select **+ Create new branch...** and type your name.
   - If you ALREADY have a branch, simply select your branch name from the list. 
   *(Note: If you switched to an existing branch, you can update it by opening the Command Palette (`Ctrl + Shift + P`), typing **Git: Merge Branch**, and selecting `main` to merge the new updates into your personal branch.)*

---

## Step 2: Work on Your Personal Branch
Now that you are on your personal branch (double-check the bottom-left corner to ensure it shows your name, not `main`), you can safely edit, add, or move files.

*(Tip: If you need to fix your folder structure by moving files from a subfolder into the root folder, you can simply drag and drop them in the VS Code Explorer!)*

---

## Step 3: Save and Push Your Changes
After you have finished making changes, use VS Code's Source Control to save them to GitHub.

1. Open the **Source Control** panel (the branch icon on the left sidebar).
2. Hover over **Changes** and click the **+ (Stage All Changes)** icon to stage your files.
3. Type a short, descriptive message in the **Message** text box explaining what you changed.
4. Click the **Commit** button.
5. Finally, click the **Publish Branch** button (or **Sync Changes** button) to push your updates to GitHub.

---

## Step 4: Create a Pull Request (PR)
Finally, ask the team to review and merge your changes into the main project.

1. Go to the repository on GitHub: https://github.com/Geotags-GMD/gmd-pipeline
2. You will usually see a green **"Compare & pull request"** button for your recently pushed branch. Click it.
3. Alternatively, go to the **Pull requests** tab and click **New pull request**. Make sure the base is `main` and the compare branch is your personal branch.
4. Add a clear title and description explaining what you changed and why.
5. Click **Create pull request**.
6. Wait for a team member to review and approve your PR!
