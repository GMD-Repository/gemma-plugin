# -*- coding: utf-8 -*-
"""
EARF Writer
-----------
Produces a styled **2026 Preliminary Enumeration Area Reference File (EARF)**
Excel workbook from the Tab 3 merged output layer.

Template layout (matching PSA census format):

  Row  1 : Title  — "2026 Preliminary Enumeration Area Reference File"
  Row  2 : Sub-title — "As of <Mmm> <YYYY>"
  Row  3 : (blank spacer)
  Row  4 : Column group headers (merged):
             Geographic Identification | 2024 EARF | 2024 Estimated |
             2026 Preliminary EAs
  Rows 5–8: Sub-header labels (merged vertically, word-wrapped)
  Row  9 : Column number codes  (1) (2) … (15)
  Row 10 : (blank spacer)
  Row 11+: Data block
             - City/Mun summary row  (bold, gray fill)
             - For each barangay:
                 Barangay summary row (bold, lighter fill)
                 EA data rows         (one per feature)

Column layout (A–O, 15 columns):
  A  Reg          — 2-digit region code
  B  Prov         — 5-digit province/city-mun code
  C  Mun          — city-mun portion
  D  Brgy         — 3-digit barangay suffix
  E  EA           — EA code (ean)
  F  Number of EAs                                         2024 EARF
  G  Province, City, Municipality, Barangay, and EA        2024 EARF
  H  Number of Households                                  2024 Estimated
  I  Number of Buildings                                   2024 Estimated
  J  New Enumeration Area Code                             2026 Preliminary EAs
  K  Number of Household                                   2026 Preliminary EAs
  L  Number of Buildings                                   2026 Preliminary EAs
  M  EA Type                                               2026 Preliminary EAs
  N  Source Year                                           2026 Preliminary EAs
  O  Remarks                                               2026 Preliminary EAs

Data sources (standard 19-field merged-layer schema):
  geocode (8-digit) → Reg / Prov / Mun / Brgy codes
  ean               → col E
  eacount           → col F
  name              → col G
  hhcount           → col H  (2024 baseline)
  bldgcount         → col I  (2024 baseline)
  new_ean           → col J
  hh_count          → col K  (2026 estimated)
  bldg_count        → col L  (2026 estimated)
  ea_type           → col M
  sy                → col N
  remarks           → col O

Delineated EAs : Each child feature appears on its own row.
Merged EAs     : Included once (prevailing EA); "Merged EA" appended to remarks.
Special EAs    : Included with ea_type as-is (GAP / OVERLAP / SPECIAL).

Dependencies: openpyxl >= 3.0
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Column indices (0-based, A=0 … O=14)
# ---------------------------------------------------------------------------
_COL_REG        = 0   # A
_COL_PROV       = 1   # B
_COL_MUN        = 2   # C
_COL_BRGY       = 3   # D
_COL_EA         = 4   # E
_COL_EACOUNT    = 5   # F
_COL_NAME       = 6   # G
_COL_HHCOUNT    = 7   # H
_COL_BLDGCOUNT  = 8   # I
_COL_NEW_EAN    = 9   # J
_COL_HH_COUNT   = 10  # K
_COL_BLDG_COUNT = 11  # L
_COL_EA_TYPE    = 12  # M
_COL_SY         = 13  # N
_COL_REMARKS    = 14  # O

_TOTAL_COLS = 15   # A–O

# ---------------------------------------------------------------------------
# Row constants (1-indexed for openpyxl)
# ---------------------------------------------------------------------------
_ROW_TITLE     = 1
_ROW_AS_OF     = 2
_ROW_SPACER1   = 3
_ROW_GRP_HDR   = 4
_ROW_SUBHDR_S  = 5   # sub-header start (rows 5–8 merged per column)
_ROW_SUBHDR_E  = 8   # sub-header end
_ROW_NUM_CODES = 9
_ROW_SPACER2   = 10
_DATA_START    = 11

# ---------------------------------------------------------------------------
# Column-group definitions  (1-indexed, inclusive)
# Format: (label, start_col, end_col)
# ---------------------------------------------------------------------------
_COL_GROUPS = [
    ("Geographic Identification", 1,  5),   # A–E
    ("2024 EARF",                 6,  7),   # F–G
    ("2024 Estimated",            8,  9),   # H–I
    ("2026 Preliminary EAs",      10, 15),  # J–O
]

# ---------------------------------------------------------------------------
# Sub-header texts per column (displayed in rows 5–8, merged vertically)
# ---------------------------------------------------------------------------
_SUBHDR = [
    "Reg",
    "Prov",
    "Mun",
    "Brgy",
    "EA",
    "Number of\nEAs",
    "Province, City, Municipality,\nBarangay, and EA",
    "Number of\nHouseholds",
    "Number of\nBuildings",
    "New Enumeration\nArea Code",
    "Number of\nHousehold",
    "Number of\nBuildings",
    "EA Type",
    "Source\nYear",
    "Remarks",
]

# Number codes row 9
_NUM_CODES = [
    "(1)", "(2)", "(3)", "(4)", "(5)",
    "(6)", "(7)", "(8)", "(9)",
    "(10)", "(11)", "(12)", "(13)", "(14)", "",
]

# Column widths (Excel character units)
_COL_WIDTHS = [
    5, 7, 5, 6, 10,    # A–E
    10, 44, 14, 12,    # F–I
    18, 14, 14, 12, 10, 32,  # J–O
]

# Numeric column indices (0-based) — right-align
_NUMERIC_COLS = {
    _COL_EACOUNT, _COL_HHCOUNT, _COL_BLDGCOUNT,
    _COL_HH_COUNT, _COL_BLDG_COUNT,
}
# Center-aligned columns (codes, type, year)
_CENTER_COLS = {
    _COL_REG, _COL_PROV, _COL_MUN, _COL_BRGY,
    _COL_EA, _COL_NEW_EAN, _COL_EA_TYPE, _COL_SY,
}


# ===========================================================================
# EARFWriter
# ===========================================================================

class EARFWriter:
    """Writes the 2026 Preliminary EARF Excel workbook.

    Parameters
    ----------
    layer : QgsVectorLayer
        The merged EA output layer (standard 19-field schema).
    geo_code : str
        5-digit geographic code (city/municipality level).
    citymun : str
        City/Municipality name used in the summary row.
    output_path : str
        Full path for the output .xlsx file.
    as_of_date : datetime, optional
        Date for the "As of <Mmm> <YYYY>" sub-title. Defaults to today.
    feedback : callable, optional
        ``callback(msg: str)`` for logging. Defaults to no-op.
    """

    def __init__(
        self,
        layer,
        geo_code: str,
        citymun: str,
        output_path: str,
        as_of_date: Optional[datetime] = None,
        feedback=None,
    ) -> None:
        self._layer       = layer
        self._geo_code    = geo_code
        self._citymun     = citymun
        self._output_path = output_path
        self._as_of_date  = as_of_date or datetime.now()
        self._log         = feedback or (lambda msg: None)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def write(self) -> bool:
        """Generate the EARF Excel file. Returns True on success."""
        try:
            import openpyxl
        except ImportError:
            self._log("[ERROR] openpyxl is not installed. Cannot generate EARF Excel.")
            return False

        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "EA2026"

            self._log("[INFO] EARF Writer: collecting data rows...")
            data_rows = self._collect_data_rows()

            styles = _Styles()
            self._log("[INFO] EARF Writer: writing title block...")
            self._write_title_block(ws, styles)

            self._log("[INFO] EARF Writer: writing column group headers...")
            self._write_group_headers(ws, styles)

            self._log("[INFO] EARF Writer: writing sub-headers...")
            self._write_sub_headers(ws, styles)

            self._log("[INFO] EARF Writer: writing data rows...")
            self._write_data_block(ws, styles, data_rows)

            # Column widths
            for col_idx, width in enumerate(_COL_WIDTHS, start=1):
                from openpyxl.utils import get_column_letter
                ws.column_dimensions[get_column_letter(col_idx)].width = width

            # Row heights for header section
            ws.row_dimensions[_ROW_TITLE].height    = 16
            ws.row_dimensions[_ROW_AS_OF].height    = 14
            ws.row_dimensions[_ROW_GRP_HDR].height  = 18
            for r in range(_ROW_SUBHDR_S, _ROW_SUBHDR_E + 1):
                ws.row_dimensions[r].height = 14
            ws.row_dimensions[_ROW_NUM_CODES].height = 13

            # Freeze panes: keep headers visible when scrolling
            ws.freeze_panes = ws.cell(row=_DATA_START, column=1)

            wb.save(self._output_path)
            self._log(f"[INFO] EARF Excel written: {self._output_path}")
            return True

        except Exception as exc:
            import traceback
            self._log(f"[ERROR] EARF Writer failed: {exc}")
            self._log(f"[ERROR] {traceback.format_exc()}")
            return False

    # ------------------------------------------------------------------
    # Data collection
    # ------------------------------------------------------------------

    def _collect_data_rows(self) -> List[Dict[str, Any]]:
        """Read features from the layer and return ordered row dicts.

        Order:
          1. City/Mun summary row
          2. For each barangay (sorted by 8-digit geocode):
             a. Barangay summary row
             b. EA rows sorted by ean
        """
        try:
            from qgis.core import NULL
        except ImportError:
            NULL = None  # allow unit testing outside QGIS

        layer  = self._layer
        fields = layer.fields()
        name_to_idx: Dict[str, int] = {
            fields.at(i).name().lower(): i for i in range(fields.count())
        }

        def _str(feat, fname: str) -> Optional[str]:
            idx = name_to_idx.get(fname.lower(), -1)
            if idx == -1:
                return None
            val = feat.attribute(idx)
            if val is None or val == NULL:
                return None
            s = str(val).strip()
            return None if s in ("", "NULL", "None") else s

        def _num(feat, fname: str) -> Optional[Any]:
            raw = _str(feat, fname)
            if raw is None:
                return None
            try:
                f = float(raw)
                return int(f) if f == int(f) else f
            except (ValueError, TypeError):
                return None

        # ── Collect raw EA rows ──────────────────────────────────────────
        raw_rows: List[Dict[str, Any]] = []
        seen_new_eans: set = set()

        for feat in layer.getFeatures():
            geocode_raw = _str(feat, "geocode") or ""
            digits = re.sub(r"\D", "", geocode_raw)

            # Parse geographic code components
            # Full geocode expected as 8-digit: RRPPPMMBBB (but QGIS stores 8 chars)
            # Breakdown: digits[0:2]=reg, full 5-digit=citymun, last 3=brgy offset
            if len(digits) >= 8:
                reg  = digits[0:2]
                prov = digits[2:5]    # 3-digit province offset within 5-digit code
                mun  = digits[0:5]    # 5-digit city/mun code
                brgy = digits[5:8]    # 3-digit barangay suffix
                geocode_8 = digits[:8]
            elif len(digits) >= 5:
                reg  = digits[0:2]
                prov = digits[2:5]
                mun  = digits[0:5]
                brgy = ""
                geocode_8 = digits[:5].ljust(8, "0")
            else:
                reg = prov = mun = brgy = ""
                geocode_8 = (digits or geocode_raw).ljust(8, "0")[:8]

            ean_val     = _str(feat, "ean")     or ""
            new_ean_val = _str(feat, "new_ean") or ""
            remarks_val = _str(feat, "remarks") or ""

            # Detect merged: remarks mentions "merge" or new_ean already emitted
            is_merged = (
                "merge" in remarks_val.lower()
                or (new_ean_val and new_ean_val in seen_new_eans)
            )
            if is_merged and "merge" not in remarks_val.lower():
                remarks_val = ("Merged EA; " + remarks_val).strip("; ")

            if new_ean_val:
                seen_new_eans.add(new_ean_val)

            raw_rows.append({
                # Geographic identifiers
                "reg":        reg,
                "prov":       prov,
                "mun":        mun,
                "brgy":       brgy,
                "ea":         ean_val,
                "geocode_8":  geocode_8,
                # 2024 EARF columns
                "eacount":    _num(feat, "eacount"),
                "name":       _str(feat, "name")     or "",
                "hhcount":    _num(feat, "hhcount"),
                "bldgcount":  _num(feat, "bldgcount"),
                # 2026 Preliminary columns
                "new_ean":    new_ean_val,
                "hh_count":   _num(feat, "hh_count"),
                "bldg_count": _num(feat, "bldg_count"),
                "ea_type":    _str(feat, "ea_type")  or "RETAINED",
                "sy":         _str(feat, "sy")        or "2026",
                "remarks":    remarks_val,
                # Row type
                "is_citymun_summary":  False,
                "is_barangay_summary": False,
                "is_ea_row":           True,
            })

        # ── City/Mun totals ──────────────────────────────────────────────
        def _sum(rows, key):
            return sum(r[key] or 0 for r in rows) or None

        first = raw_rows[0] if raw_rows else {}
        citymun_row = {
            "reg":    first.get("reg",  ""),
            "prov":   first.get("prov", ""),
            "mun":    first.get("mun",  ""),
            "brgy":   "000",
            "ea":     "000000",
            "geocode_8": self._geo_code.ljust(8, "0")[:8],
            "eacount":   _sum(raw_rows, "eacount"),
            "name":      self._citymun.upper(),
            "hhcount":   _sum(raw_rows, "hhcount"),
            "bldgcount": _sum(raw_rows, "bldgcount"),
            "new_ean":   "",
            "hh_count":  _sum(raw_rows, "hh_count"),
            "bldg_count":_sum(raw_rows, "bldg_count"),
            "ea_type":   "",
            "sy":        "",
            "remarks":   "",
            "is_citymun_summary":  True,
            "is_barangay_summary": False,
            "is_ea_row":           False,
        }

        # ── Group by barangay ────────────────────────────────────────────
        brgy_groups: Dict[str, List[Dict]] = {}
        for r in raw_rows:
            brgy_groups.setdefault(r["geocode_8"], []).append(r)

        # ── Build ordered output ─────────────────────────────────────────
        output: List[Dict[str, Any]] = [citymun_row]

        for brgy_code in sorted(brgy_groups.keys()):
            ea_rows = brgy_groups[brgy_code]
            first_ea = ea_rows[0]

            # Derive barangay name by stripping EA suffix from the name field
            brgy_name = first_ea.get("name", "")
            brgy_name = re.sub(
                r"\s*[-\u2013]\s*EA\s+\S+\s*$", "", brgy_name, flags=re.IGNORECASE
            ).strip()

            brgy_row = {
                "reg":    first_ea.get("reg",  ""),
                "prov":   first_ea.get("prov", ""),
                "mun":    first_ea.get("mun",  ""),
                "brgy":   first_ea.get("brgy", ""),
                "ea":     "000000",
                "geocode_8": brgy_code,
                "eacount":   _sum(ea_rows, "eacount"),
                "name":      brgy_name,
                "hhcount":   _sum(ea_rows, "hhcount"),
                "bldgcount": _sum(ea_rows, "bldgcount"),
                "new_ean":   "",
                "hh_count":  _sum(ea_rows, "hh_count"),
                "bldg_count":_sum(ea_rows, "bldg_count"),
                "ea_type":   "",
                "sy":        "",
                "remarks":   "",
                "is_citymun_summary":  False,
                "is_barangay_summary": True,
                "is_ea_row":           False,
            }
            output.append(brgy_row)

            for ea_row in sorted(ea_rows, key=lambda r: r.get("ea", "") or ""):
                output.append(ea_row)

        return output

    # ------------------------------------------------------------------
    # Section writers
    # ------------------------------------------------------------------

    def _write_title_block(self, ws, styles) -> None:
        """Rows 1–3: title, as-of date, blank spacer."""
        # Row 1
        cell = ws.cell(row=_ROW_TITLE, column=1,
                       value="2026 Preliminary Enumeration Area Reference File")
        cell.font      = styles.font_title
        cell.alignment = styles.align_left
        ws.merge_cells(
            start_row=_ROW_TITLE, start_column=1,
            end_row=_ROW_TITLE,   end_column=_TOTAL_COLS,
        )

        # Row 2
        as_of_str = self._as_of_date.strftime("As of %b %Y")
        cell2 = ws.cell(row=_ROW_AS_OF, column=1, value=as_of_str)
        cell2.font      = styles.font_normal_bold
        cell2.alignment = styles.align_left
        ws.merge_cells(
            start_row=_ROW_AS_OF, start_column=1,
            end_row=_ROW_AS_OF,   end_column=_TOTAL_COLS,
        )
        # Row 3 — spacer, leave blank

    def _write_group_headers(self, ws, styles) -> None:
        """Row 4: merged column-group header cells."""
        group_fills = {
            "Geographic Identification": styles.fill_geo,
            "2024 EARF":                 styles.fill_2024,
            "2024 Estimated":            styles.fill_est,
            "2026 Preliminary EAs":      styles.fill_2026,
        }

        for label, start_col, end_col in _COL_GROUPS:
            fill = group_fills[label]

            # Write label in the first cell of the group
            cell = ws.cell(row=_ROW_GRP_HDR, column=start_col, value=label)
            cell.font      = styles.font_group_hdr
            cell.alignment = styles.align_center
            cell.border    = styles.border_thin

            # Merge if multi-column
            if start_col < end_col:
                ws.merge_cells(
                    start_row=_ROW_GRP_HDR, start_column=start_col,
                    end_row=_ROW_GRP_HDR,   end_column=end_col,
                )

            # Apply fill to every cell in the merged range
            for c in range(start_col, end_col + 1):
                mc = ws.cell(row=_ROW_GRP_HDR, column=c)
                mc.fill   = fill
                mc.border = styles.border_thin

    def _write_sub_headers(self, ws, styles) -> None:
        """Rows 5–8 (merged vertically) + row 9 number codes."""
        for col_idx, label in enumerate(_SUBHDR, start=1):
            # Write label in the first row; merge rows 5–8
            cell = ws.cell(row=_ROW_SUBHDR_S, column=col_idx, value=label)
            cell.font      = styles.font_subhdr
            cell.alignment = styles.align_center_wrap
            cell.fill      = styles.fill_subhdr
            cell.border    = styles.border_thin

            ws.merge_cells(
                start_row=_ROW_SUBHDR_S, start_column=col_idx,
                end_row=_ROW_SUBHDR_E,   end_column=col_idx,
            )
            # Apply fill/border to all merged cells
            for r in range(_ROW_SUBHDR_S, _ROW_SUBHDR_E + 1):
                mc = ws.cell(row=r, column=col_idx)
                mc.fill   = styles.fill_subhdr
                mc.border = styles.border_thin

        # Row 9 — number codes
        for col_idx, code in enumerate(_NUM_CODES, start=1):
            cell = ws.cell(row=_ROW_NUM_CODES, column=col_idx, value=code)
            cell.font      = styles.font_num_code
            cell.alignment = styles.align_center
            cell.fill      = styles.fill_subhdr
            cell.border    = styles.border_thin

    def _write_data_block(self, ws, styles,
                          data_rows: List[Dict[str, Any]]) -> None:
        """Write city/mun summary, barangay summaries, and EA rows."""
        for offset, row_data in enumerate(data_rows):
            row = _DATA_START + offset
            if row_data["is_citymun_summary"]:
                self._write_row(ws, styles, row, row_data, kind="citymun")
            elif row_data["is_barangay_summary"]:
                self._write_row(ws, styles, row, row_data, kind="barangay")
            else:
                self._write_row(ws, styles, row, row_data, kind="ea")

    def _write_row(self, ws, styles, row: int,
                   row_data: Dict, kind: str) -> None:
        """Write a single row; kind = 'citymun' | 'barangay' | 'ea'."""
        if kind == "citymun":
            font   = styles.font_summary_citymun
            fill   = styles.fill_summary_citymun
            border = styles.border_thin
        elif kind == "barangay":
            font   = styles.font_summary_brgy
            fill   = styles.fill_summary_brgy
            border = styles.border_thin
        else:
            font   = styles.font_data
            fill   = styles.fill_none
            border = styles.border_thin_light

        values = [
            row_data.get("reg",        ""),
            row_data.get("prov",       ""),
            row_data.get("mun",        ""),
            row_data.get("brgy",       ""),
            row_data.get("ea",         ""),
            row_data.get("eacount"),
            row_data.get("name",       ""),
            row_data.get("hhcount"),
            row_data.get("bldgcount"),
            row_data.get("new_ean",    ""),
            row_data.get("hh_count"),
            row_data.get("bldg_count"),
            row_data.get("ea_type",    ""),
            row_data.get("sy",         ""),
            row_data.get("remarks",    ""),
        ]

        for col_idx, val in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col_idx, value=val)
            cell.font   = font
            cell.fill   = fill
            cell.border = border

            zero = col_idx - 1  # 0-based column index
            if zero in _NUMERIC_COLS:
                cell.alignment = styles.align_right
            elif zero in _CENTER_COLS:
                cell.alignment = styles.align_center
            else:
                cell.alignment = styles.align_left


# ===========================================================================
# _Styles — centralised openpyxl style objects
# ===========================================================================

class _Styles:
    """Create and cache all openpyxl style objects used by EARFWriter."""

    def __init__(self) -> None:
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

        # ── Fonts ────────────────────────────────────────────────────────
        self.font_title           = Font(name="Arial", size=12, bold=True)
        self.font_normal_bold     = Font(name="Arial", size=10, bold=True)
        self.font_group_hdr       = Font(name="Arial", size=9,  bold=True)
        self.font_subhdr          = Font(name="Arial", size=8,  bold=True)
        self.font_num_code        = Font(name="Arial", size=8,  bold=False)
        self.font_summary_citymun = Font(name="Arial", size=9,  bold=True)
        self.font_summary_brgy    = Font(name="Arial", size=8,  bold=True)
        self.font_data            = Font(name="Arial", size=8)

        # ── Alignments ───────────────────────────────────────────────────
        self.align_left         = Alignment(horizontal="left",   vertical="center")
        self.align_center       = Alignment(horizontal="center", vertical="center")
        self.align_right        = Alignment(horizontal="right",  vertical="center")
        self.align_center_wrap  = Alignment(horizontal="center", vertical="center",
                                            wrap_text=True)

        # ── Fills ────────────────────────────────────────────────────────
        def _fill(hex_color: str) -> PatternFill:
            return PatternFill(fill_type="solid", fgColor=hex_color)

        self.fill_geo             = _fill("E2EFDA")   # Geographic ID — soft green
        self.fill_2024            = _fill("D6E4BC")   # 2024 EARF — light green
        self.fill_est             = _fill("FFFFC1")   # 2024 Estimated — light yellow
        self.fill_2026            = _fill("C5D9F1")   # 2026 Preliminary — light blue
        self.fill_subhdr          = _fill("F2F2F2")   # Sub-header — light gray
        self.fill_summary_citymun = _fill("D9D9D9")   # City/Mun row — medium gray
        self.fill_summary_brgy    = _fill("EFEFEF")   # Barangay row — lighter gray
        self.fill_none            = PatternFill(fill_type=None)

        # ── Borders ──────────────────────────────────────────────────────
        _thin  = Side(style="thin")
        _hair  = Side(style="hair")

        self.border_thin = Border(
            left=_thin, right=_thin, top=_thin, bottom=_thin,
        )
        self.border_thin_light = Border(
            left=_hair, right=_hair, top=_hair, bottom=_hair,
        )
