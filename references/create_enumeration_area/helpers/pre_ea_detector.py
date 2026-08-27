# -*- coding: utf-8 -*-
"""
Helper module for automatic detection of generated EA input folders and layers
from the standard PSA-GIS / Project 1MAP directory hierarchy.
"""

import os
import re
import string
from typing import List, Dict, Tuple, Optional

try:
    from qgis.PyQt.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QListWidget, QListWidgetItem, QRadioButton, QButtonGroup,
        QDialogButtonBox, QFrame, QScrollArea, QWidget
    )
    from qgis.PyQt.QtCore import Qt, QDir
    from qgis.PyQt.QtGui import QFont, QIcon
except ImportError:
    # Allow running in non-GUI mock / test environments
    QDialog = object
    Qt = None


def detect_available_drives() -> List[str]:
    """
    Dynamically discover all available root drives on the system.
    Supports Windows drive letters (A-Z) and Unix-like root paths.
    """
    drives = []

    # Check Qt QDir.drives() if available
    try:
        if Qt is not None:
            qt_drives = [d.absoluteFilePath() for d in QDir.drives()]
            for d in qt_drives:
                if d and os.path.exists(d) and d not in drives:
                    drives.append(d)
    except Exception:
        pass

    # Windows drive letters fallback/scan
    if os.name == 'nt' or os.path.exists('C:\\'):
        for letter in string.ascii_uppercase:
            drive_root = f"{letter}:\\"
            if os.path.exists(drive_root) and drive_root not in drives:
                drives.append(drive_root)

    # Unix fallback
    if not drives and os.path.exists('/'):
        drives.append('/')

    return drives


def get_unique_filepath(directory: str, base_name: str, ext: str = ".gpkg") -> str:
    """Generate a unique file path by appending (1), (2), etc. if the file exists and is locked."""
    candidate = os.path.normpath(os.path.join(directory, f"{base_name}{ext}")).replace("\\", "/")
    if not os.path.exists(candidate):
        return candidate

    # Attempt to remove if existing and not locked by QGIS or another process
    try:
        os.remove(candidate)
        return candidate
    except Exception:
        pass

    # Browser-style auto-numbering (1), (2), (3)...
    counter = 1
    while True:
        candidate = os.path.normpath(os.path.join(directory, f"{base_name} ({counter}){ext}")).replace("\\", "/")
        if not os.path.exists(candidate):
            return candidate
        try:
            os.remove(candidate)
            return candidate
        except Exception:
            counter += 1


def _normalize_name(name: str) -> str:
    """Normalize a directory or file name for fuzzy comparison."""
    if not name:
        return ""
    return name.lower().replace("-", "").replace("_", "").replace("&", "and").replace(" ", "")


def _find_matching_child_dir(parent_dir: str, target_name: str) -> Optional[str]:
    """Find a child directory matching target_name (tolerant of case, spaces, dashes, and underscores)."""
    if not os.path.isdir(parent_dir):
        return None
    try:
        norm_target = _normalize_name(target_name)
        exact_lower = target_name.strip().lower()

        # 1. Exact case-insensitive match
        for entry in os.listdir(parent_dir):
            if entry.lower() == exact_lower:
                candidate = os.path.join(parent_dir, entry)
                if os.path.isdir(candidate):
                    return candidate

        # 2. Normalized match (ignoring dashes, underscores, spaces, & vs and)
        for entry in os.listdir(parent_dir):
            if _normalize_name(entry) == norm_target:
                candidate = os.path.join(parent_dir, entry)
                if os.path.isdir(candidate):
                    return candidate

        # 3. Pattern match for standard directory keywords
        if "preprocessing" in norm_target:
            for entry in os.listdir(parent_dir):
                e_norm = _normalize_name(entry)
                if "preprocessing" in e_norm:
                    candidate = os.path.join(parent_dir, entry)
                    if os.path.isdir(candidate):
                        return candidate

        if "resetea" in norm_target:
            for entry in os.listdir(parent_dir):
                e_norm = _normalize_name(entry)
                if "resetea" in e_norm or "1reset" in e_norm:
                    candidate = os.path.join(parent_dir, entry)
                    if os.path.isdir(candidate):
                        return candidate

        if "adjustedea" in norm_target:
            for entry in os.listdir(parent_dir):
                e_norm = _normalize_name(entry)
                if "adjustedea" in e_norm or "2adjusted" in e_norm:
                    candidate = os.path.join(parent_dir, entry)
                    if os.path.isdir(candidate):
                        return candidate

        if "delineation" in norm_target:
            for entry in os.listdir(parent_dir):
                e_norm = _normalize_name(entry)
                if "delineation" in e_norm:
                    candidate = os.path.join(parent_dir, entry)
                    if os.path.isdir(candidate):
                        return candidate

        if "1map" in norm_target:
            for entry in os.listdir(parent_dir):
                e_norm = _normalize_name(entry)
                if "1map" in e_norm:
                    candidate = os.path.join(parent_dir, entry)
                    if os.path.isdir(candidate):
                        return candidate

    except (OSError, PermissionError):
        return None
    return None


def extract_province_and_citymun(layer) -> Tuple[str, str]:
    """Extract (province_name, citymun_name) from a layer's attributes if available."""
    prov_val = ""
    citymun_val = ""
    if not layer or not hasattr(layer, 'fields') or not hasattr(layer, 'getFeatures'):
        return prov_val, citymun_val

    try:
        prov_fields = ("province", "prov_name", "prov", "province_name", "adm2_name", "adm2_en")
        citymun_fields = ("citymun", "city_mun", "city", "municipality", "mun_name", "adm3_name", "adm3_en", "city_name")

        prov_field_name = None
        citymun_field_name = None

        for f in layer.fields():
            fn = f.name().lower()
            if not prov_field_name and fn in prov_fields:
                prov_field_name = f.name()
            if not citymun_field_name and fn in citymun_fields:
                citymun_field_name = f.name()

        feat = next(layer.getFeatures(), None)
        if feat:
            if prov_field_name:
                p = str(feat.attribute(prov_field_name)).strip()
                if p and p.lower() != "null":
                    prov_val = p
            if citymun_field_name:
                c = str(feat.attribute(citymun_field_name)).strip()
                if c and c.lower() != "null":
                    citymun_val = c
    except Exception:
        pass

    return prov_val, citymun_val


def detect_project_from_layer(layer, subfolder_name: Optional[str] = None) -> Optional[str]:
    """
    Attempt to detect the Pre-Processing folder from an input layer's source filepath,
    province, or city/municipality attributes using regex and folder matching.
    Matches standard hierarchy:
    <DRIVE>:\\PSA-GIS\\<Province Name or CityMun or CO>\\Project 1MAP\\3_EA Delineation and Merging\\2_Pre-Processing\\<subfolder>
    """
    if not layer:
        return None

    # Method 1: Regex pattern extraction on layer source path
    try:
        src = getattr(layer, 'source', lambda: '')() if hasattr(layer, 'source') else ''
        if src and isinstance(src, str):
            clean_path = src.split("|")[0].strip().replace("/", "\\")

            # Regex 1: Matches <drive>:\PSA-GIS\<CO or Province or CityMun>\...
            m1 = re.search(r"^(?P<drive>[a-zA-Z]:)[/\\]PSA-GIS[/\\](?P<root>[^/\\]+)", clean_path, re.IGNORECASE)
            if m1:
                root_name = m1.group("root")
                # Filter out auxiliary utility folders like 'Activity', 'Important', etc.
                if root_name.lower() not in ("activity", "geopackage", "important", "temporary files", "temp", "scratch"):
                    drive = m1.group("drive")
                    target = os.path.join(drive, "\\PSA-GIS", root_name, "Project 1MAP", "3_EA Delineation and Merging", "2_Pre-Processing")
                    return os.path.join(target, subfolder_name) if subfolder_name else target

            # Regex 2: Matches any path containing Project 1MAP
            m2 = re.search(r"^(?P<prefix>.*?[/\\]Project\s*1MAP)", clean_path, re.IGNORECASE)
            if m2:
                root_prefix = m2.group("prefix")
                # Ensure prefix doesn't originate inside an ignored utility folder
                if "activity" not in root_prefix.lower() and "important" not in root_prefix.lower() and "temporary" not in root_prefix.lower():
                    target = os.path.join(root_prefix, "3_EA Delineation and Merging", "2_Pre-Processing")
                    return os.path.join(target, subfolder_name) if subfolder_name else target
    except Exception:
        pass

    # Extract province and city/municipality attributes from layer
    prov_val, citymun_val = extract_province_and_citymun(layer)
    norm_prov = _normalize_name(prov_val) if prov_val else ""
    norm_city = _normalize_name(citymun_val) if citymun_val else ""

    # Method 2: Match equal Province Name or City/Municipality across available drives
    try:
        for drive in detect_available_drives():
            psa_gis = os.path.join(drive, "PSA-GIS")
            if not os.path.isdir(psa_gis):
                continue

            try:
                entries = os.listdir(psa_gis)
            except (OSError, PermissionError):
                continue

            # Check for direct province folder match
            if norm_prov:
                for entry in entries:
                    if _normalize_name(entry) == norm_prov or entry.lower() == prov_val.lower():
                        prov_dir = os.path.join(psa_gis, entry)
                        target = os.path.join(prov_dir, "Project 1MAP", "3_EA Delineation and Merging", "2_Pre-Processing")
                        return os.path.join(target, subfolder_name) if subfolder_name else target

            # Check for direct city/municipality folder match
            if norm_city:
                for entry in entries:
                    if _normalize_name(entry) == norm_city or entry.lower() == citymun_val.lower():
                        city_dir = os.path.join(psa_gis, entry)
                        target = os.path.join(city_dir, "Project 1MAP", "3_EA Delineation and Merging", "2_Pre-Processing")
                        return os.path.join(target, subfolder_name) if subfolder_name else target

            # Check inside CO for province or citymun match
            co_dir = os.path.join(psa_gis, "CO")
            if os.path.isdir(co_dir):
                try:
                    co_entries = os.listdir(co_dir)
                    if norm_prov:
                        for entry in co_entries:
                            if _normalize_name(entry) == norm_prov or entry.lower() == prov_val.lower():
                                prov_in_co = os.path.join(co_dir, entry)
                                target = os.path.join(prov_in_co, "Project 1MAP", "3_EA Delineation and Merging", "2_Pre-Processing")
                                return os.path.join(target, subfolder_name) if subfolder_name else target
                except (OSError, PermissionError):
                    pass
    except Exception:
        pass

    # Method 3: Check for CO on available drives (e.g. D:\PSA-GIS\CO\Project 1MAP\3_EA Delineation and Merging\2_Pre-Processing)
    try:
        for drive in detect_available_drives():
            co_target = os.path.join(drive, "PSA-GIS", "CO", "Project 1MAP", "3_EA Delineation and Merging", "2_Pre-Processing")
            co_root = os.path.join(drive, "PSA-GIS", "CO")
            if os.path.isdir(co_target) or os.path.isdir(co_root):
                return os.path.join(co_target, subfolder_name) if subfolder_name else co_target
    except Exception:
        pass

    # Method 4: Fallback default construct using Province, CityMun, or CO
    drives = detect_available_drives()
    first_drive = drives[0] if drives else "C:\\"
    fallback_name = prov_val or citymun_val or "CO"
    fallback_target = os.path.join(first_drive, "PSA-GIS", fallback_name, "Project 1MAP", "3_EA Delineation and Merging", "2_Pre-Processing")
    return os.path.join(fallback_target, subfolder_name) if subfolder_name else fallback_target


def scan_psa_gis_projects(custom_drives: Optional[List[str]] = None) -> Tuple[List[Dict[str, str]], Dict[str, bool]]:
    """
    Scan available drives for PSA-GIS project preprocessing locations.

    Expected structure:
    <DRIVE>:\\PSA-GIS\\<PROVINCE>\\Project 1MAP\\3_EA Delineation and Merging\\2_Pre-Processing

    Returns:
        (valid_projects, diagnostics)
    """
    drives = custom_drives if custom_drives is not None else detect_available_drives()
    valid_projects = []
    diagnostics = {
        'psa_gis_found': False,
        'project_1map_found': False,
        'prep_found': False
    }

    p1_name = "Project 1MAP"
    p2_name = "3_EA Delineation and Merging"
    p3_name = "2_Pre-Processing"

    # Known utility folders to ignore unless they explicitly contain Project 1MAP
    ignore_folders = {"activity", "geopackage", "important", "temporary files", "temp", "archive", "backup"}

    for drive in drives:
        psa_gis_candidate = _find_matching_child_dir(drive, "PSA-GIS")
        if not psa_gis_candidate:
            direct_psa = os.path.join(drive, "PSA-GIS")
            if os.path.isdir(direct_psa):
                psa_gis_candidate = direct_psa

        if not psa_gis_candidate:
            continue

        diagnostics['psa_gis_found'] = True

        try:
            entries = os.listdir(psa_gis_candidate)
        except (OSError, PermissionError):
            continue

        # Check CO first if present, filter out utility folders
        ordered_entries = []
        for e in entries:
            norm_e = _normalize_name(e)
            if e.upper() == "CO":
                ordered_entries.insert(0, e)
            elif norm_e not in ignore_folders and not any(ign in norm_e for ign in ("activity", "geopackage", "important", "temporary", "temp")):
                ordered_entries.append(e)

        for province_entry in ordered_entries:
            prov_dir = os.path.join(psa_gis_candidate, province_entry)
            if not os.path.isdir(prov_dir):
                continue

            # Look for "Project 1MAP"
            p1_dir = _find_matching_child_dir(prov_dir, p1_name)
            if not p1_dir and os.path.isdir(os.path.join(prov_dir, p1_name)):
                p1_dir = os.path.join(prov_dir, p1_name)

            # Check inside CO for sub-provinces if prov_dir is CO
            if not p1_dir and province_entry.upper() == "CO":
                try:
                    for co_sub in os.listdir(prov_dir):
                        co_sub_dir = os.path.join(prov_dir, co_sub)
                        if os.path.isdir(co_sub_dir):
                            co_p1 = _find_matching_child_dir(co_sub_dir, p1_name) or os.path.join(co_sub_dir, p1_name)
                            if os.path.isdir(co_p1):
                                p2_dir = _find_matching_child_dir(co_p1, p2_name) or os.path.join(co_p1, p2_name)
                                prep_dir = _find_matching_child_dir(p2_dir, p3_name) or os.path.join(p2_dir, p3_name)
                                diagnostics['project_1map_found'] = True
                                diagnostics['prep_found'] = True
                                valid_projects.append({
                                    'drive': drive,
                                    'province': f"CO/{co_sub}",
                                    'psa_gis': psa_gis_candidate,
                                    'prep_dir': prep_dir
                                })
                except (OSError, PermissionError):
                    pass

            if not p1_dir:
                continue

            diagnostics['project_1map_found'] = True

            # Look for "3_EA Delineation and Merging" (or resolve expected path)
            p2_dir = _find_matching_child_dir(p1_dir, p2_name)
            if not p2_dir:
                p2_dir = os.path.join(p1_dir, p2_name)

            # Look for "2_Pre-Processing" (or resolve expected path)
            prep_dir = _find_matching_child_dir(p2_dir, p3_name)
            if not prep_dir:
                prep_dir = os.path.join(p2_dir, p3_name)

            diagnostics['prep_found'] = True
            valid_projects.append({
                'drive': drive,
                'province': province_entry,
                'psa_gis': psa_gis_candidate,
                'prep_dir': prep_dir
            })

    return valid_projects, diagnostics


def resolve_target_output_folder(selected_folder: str, has_ea_input: bool) -> str:
    """
    Derive the target output folder path for Pre-EA processing:
    - If has_ea_input is False -> ensure path points to "1_Reset EAs"
    - If has_ea_input is True  -> ensure path points to "2_Adjusted EAs"
    """
    if not selected_folder:
        return ""

    clean = os.path.normpath(selected_folder.strip()).replace("\\", "/")
    target_sub = "2_Adjusted EAs" if has_ea_input else "1_Reset EAs"
    other_sub = "1_Reset EAs" if has_ea_input else "2_Adjusted EAs"

    clean_lower = clean.lower()

    # 1. If path ends with the opposite subfolder, replace with target subfolder
    if clean_lower.endswith("/" + _normalize_name(other_sub)) or clean_lower.endswith(f"/{other_sub.lower()}"):
        parent = os.path.dirname(clean)
        return os.path.normpath(os.path.join(parent, target_sub)).replace("\\", "/")

    # 2. If path already ends with the target subfolder, keep it
    if clean_lower.endswith("/" + _normalize_name(target_sub)) or clean_lower.endswith(f"/{target_sub.lower()}"):
        return clean

    # 3. If target subfolder exists as a child or needs to be appended
    existing = _find_matching_child_dir(clean, target_sub)
    if existing:
        return os.path.normpath(existing).replace("\\", "/")
    return os.path.normpath(os.path.join(clean, target_sub)).replace("\\", "/")


def find_generated_ea_layer(prep_dir: str, has_ea_input: bool) -> Tuple[str, Optional[str], str]:
    """
    Locate the generated EA layer within the Pre-Processing folder based on
    whether an EA input layer is provided.

    If has_ea_input is False -> scans "1_Reset EAs"
    If has_ea_input is True  -> scans "2_Adjusted EAs"

    Returns:
        (target_folder_path, detected_file_path, status_code)
        status_code is one of: 'OK', 'FOLDER_NOT_FOUND', 'LAYER_NOT_FOUND'
    """
    target_subfolder_name = "2_Adjusted EAs" if has_ea_input else "1_Reset EAs"
    
    ea_folder = _find_matching_child_dir(prep_dir, target_subfolder_name)
    if not ea_folder:
        direct_folder = os.path.join(prep_dir, target_subfolder_name)
        if os.path.isdir(direct_folder):
            ea_folder = direct_folder
        else:
            return os.path.join(prep_dir, target_subfolder_name), None, "FOLDER_NOT_FOUND"

    try:
        files = os.listdir(ea_folder)
    except (OSError, PermissionError):
        return ea_folder, None, "FOLDER_NOT_FOUND"

    # Search for vector layers (.gpkg, .shp, .geojson)
    # Prefer .gpkg, then .shp
    gpkg_candidates = []
    shp_candidates = []
    other_candidates = []

    for f in files:
        f_lower = f.lower()
        full_path = os.path.join(ea_folder, f)
        if os.path.isfile(full_path):
            if f_lower.endswith(".gpkg"):
                gpkg_candidates.append(full_path)
            elif f_lower.endswith(".shp"):
                shp_candidates.append(full_path)
            elif f_lower.endswith(".geojson") or f_lower.endswith(".json"):
                other_candidates.append(full_path)

    # Sort each list putting names with 'ea' first
    def _ea_sort_key(filepath: str):
        basename = os.path.basename(filepath).lower()
        # priority: has 'ea' -> 0, else 1, then name
        return (0 if 'ea' in basename else 1, basename)

    gpkg_candidates.sort(key=_ea_sort_key)
    shp_candidates.sort(key=_ea_sort_key)
    other_candidates.sort(key=_ea_sort_key)

    chosen_file = None
    if gpkg_candidates:
        chosen_file = gpkg_candidates[0]
    elif shp_candidates:
        chosen_file = shp_candidates[0]
    elif other_candidates:
        chosen_file = other_candidates[0]

    if not chosen_file:
        return ea_folder, None, "LAYER_NOT_FOUND"

    return ea_folder, chosen_file, "OK"


class ProjectLocationDialog(QDialog):
    """
    Modal dialog allowing the user to select from multiple detected PSA-GIS project locations.
    """
    def __init__(self, projects: List[Dict[str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Project Location")
        self.setMinimumWidth(520)
        self.setMinimumHeight(320)
        self.projects = projects
        self.selected_index = 0

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header_lbl = QLabel("Multiple valid EA Preprocessing folders were found:")
        header_lbl.setFont(QFont("Segoe UI", 10, QFont.Bold))
        layout.addWidget(header_lbl)

        sub_lbl = QLabel("Please select the target province / project location to use:")
        sub_lbl.setStyleSheet("color: #555;")
        layout.addWidget(sub_lbl)

        # Scrollable list of radio options
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.StyledPanel)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(8, 8, 8, 8)
        scroll_layout.setSpacing(8)

        self.btn_group = QButtonGroup(self)
        for idx, proj in enumerate(self.projects):
            prov = proj.get("province", "Unknown")
            prep_dir = proj.get("prep_dir", "")
            
            container = QFrame()
            container.setFrameShape(QFrame.StyledPanel)
            container.setStyleSheet(
                "QFrame { border: 1px solid #d0d7de; border-radius: 6px; padding: 6px; background-color: #f6f8fa; }"
                "QFrame:hover { border-color: #0969da; background-color: #f0f7ff; }"
            )
            c_layout = QVBoxLayout(container)
            c_layout.setContentsMargins(6, 4, 6, 4)
            c_layout.setSpacing(2)

            rb = QRadioButton(prov)
            rb.setFont(QFont("Segoe UI", 10, QFont.Bold))
            if idx == 0:
                rb.setChecked(True)
            self.btn_group.addButton(rb, idx)
            c_layout.addWidget(rb)

            path_lbl = QLabel(prep_dir)
            path_lbl.setWordWrap(True)
            path_lbl.setFont(QFont("Segoe UI", 8))
            path_lbl.setStyleSheet("color: #656d76; margin-left: 20px;")
            c_layout.addWidget(path_lbl)

            scroll_layout.addWidget(container)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        # Button box
        bbox = QHBoxLayout()
        bbox.addStretch()

        select_btn = QPushButton("Select")
        select_btn.setDefault(True)
        select_btn.setStyleSheet(
            "QPushButton { background-color: #0969da; color: white; font-weight: bold; border-radius: 4px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #0854b0; }"
        )
        select_btn.clicked.connect(self.accept)
        bbox.addWidget(select_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            "QPushButton { border: 1px solid #d0d7de; border-radius: 4px; padding: 6px 14px; background-color: #fff; }"
            "QPushButton:hover { background-color: #f3f4f6; }"
        )
        cancel_btn.clicked.connect(self.reject)
        bbox.addWidget(cancel_btn)

        layout.addLayout(bbox)

    def get_selected_project(self) -> Optional[Dict[str, str]]:
        if self.result() == QDialog.Accepted:
            selected_id = self.btn_group.checkedId()
            if 0 <= selected_id < len(self.projects):
                return self.projects[selected_id]
        return None
