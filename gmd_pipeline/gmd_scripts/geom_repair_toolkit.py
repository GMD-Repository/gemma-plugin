# =============================================================================
# GEOMETRY VALIDATION AND REPAIR TOOLKIT v1.0.1
# Tools:
#   Tab 1 — Geometry Checker 
# =============================================================================

from qgis.PyQt.QtCore import QVariant, QThread, pyqtSignal, Qt
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QTextEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QGroupBox, QCheckBox, QListWidget,
    QListWidgetItem, QAbstractItemView, QWidget, QFrame,
    QTabWidget, QComboBox, QSizePolicy, QRadioButton, QButtonGroup,
    QStackedWidget
)
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsWkbTypes,
    QgsFeatureRequest, QgsFeature, QgsFields, QgsField,
    QgsFeatureSink, QgsMemoryProviderUtils, QgsGeometry,
    QgsProcessingContext, QgsProcessingFeedback,
    QgsProcessingFeatureSourceDefinition, QgsSpatialIndex,
    QgsProcessingUtils
)
from qgis.utils import iface
import processing


# =============================================================================
# SHARED CONSTANTS & HELPERS
# =============================================================================

BTN_RUN    = ""
BTN_CANCEL = ""
BTN_EXPORT = ""
BTN_CLEAR  = ""
GRP_STYLE  = "QGroupBox { font-weight:600; margin-top:6px; } QGroupBox::title { subcontrol-origin:margin; left:8px; }"
LOG_STYLE  = "background:#eceff1; font-family:Consolas,monospace; font-size:11px;"


def colored_item(text, issue_type=None):
    # Professional UI: no issue-specific row colors.
    item = QTableWidgetItem(text)
    if issue_type:
        f = item.font()
        f.setBold(True)
        item.setFont(f)
    return item


def make_progress():
    pb = QProgressBar()
    pb.setRange(0, 100); pb.setValue(0); pb.setFixedHeight(18)
    return pb


def get_polygon_layers():
    return {
        lyr.id(): lyr
        for lyr in QgsProject.instance().mapLayers().values()
        if isinstance(lyr, QgsVectorLayer)
        and lyr.geometryType() == QgsWkbTypes.PolygonGeometry
    }


def resolve_processing_output_layer(output_value, context):
    """Return a QgsVectorLayer whether Processing returns a layer object or a layer id/path string."""
    if isinstance(output_value, QgsVectorLayer):
        return output_value
    return QgsProcessingUtils.mapLayerFromString(output_value, context)


# =============================================================================
# TAB 1 — GEOMETRY CHECKER WORKER
# =============================================================================

class CheckWorker(QThread):
    progress    = pyqtSignal(int)
    issue_found = pyqtSignal(dict)
    log         = pyqtSignal(str)
    finished    = pyqtSignal(int)

    def __init__(self, layers, checks):
        super().__init__()
        self.layers = layers; self.checks = checks; self._cancel = False

    def cancel(self): self._cancel = True

    def run(self):
        grand = 0; n = len(self.layers)
        for li, layer in enumerate(self.layers):
            if self._cancel: break
            self.log.emit(f"Scanning: {layer.name()}  ({layer.featureCount()} features)")
            lg_type = QgsWkbTypes.geometryType(layer.wkbType())
            lg_name = QgsWkbTypes.displayString(layer.wkbType())
            counts  = {"Null Geometry":0,"Empty/Missing Geometry":0,"Wrong-type Geometry":0,"Invalid Geometry":0}
            req = QgsFeatureRequest().setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)
            for feat in layer.getFeatures(req):
                if self._cancel: break
                geom = feat.geometry()
                fg_name = "N/A"
                if geom is not None:
                    try: fg_name = QgsWkbTypes.displayString(geom.wkbType())
                    except: fg_name = "Unknown"
                issue = None
                if self.checks["null"] and (geom is None or geom.isNull()):
                    issue = "Null Geometry"
                elif self.checks["empty"] and geom is not None and not geom.isNull() \
                        and (geom.isEmpty() or geom.wkbType() == QgsWkbTypes.Unknown):
                    issue = "Empty/Missing Geometry"
                elif self.checks["wrong"] and geom is not None and not geom.isNull() \
                        and not geom.isEmpty() \
                        and QgsWkbTypes.geometryType(geom.wkbType()) != lg_type:
                    issue = "Wrong-type Geometry"
                elif self.checks["invalid"] and geom is not None and not geom.isNull() \
                        and not geom.isEmpty():
                    try:
                        if not geom.isGeosValid(): issue = "Invalid Geometry"
                    except: issue = "Invalid Geometry"
                if issue:
                    counts[issue] += 1; grand += 1
                    self.issue_found.emit({"layer":layer,"layer_name":layer.name(),
                        "feature_id":feat.id(),"issue_type":issue,
                        "layer_geom_type":lg_name,"feature_geom_type":fg_name,"geometry":geom})
            for lbl, cnt in counts.items():
                if cnt: self.log.emit(f"   {lbl}: {cnt}")
            self.progress.emit(int(((li+1)/n)*100))
        self.log.emit(f"\nFinished. Total issues: {grand}")
        self.finished.emit(grand)


# =============================================================================
# TAB 1 — GEOMETRY CHECKER UI
# =============================================================================

class CheckerTab(QWidget):
    def __init__(self):
        super().__init__()
        self.issues = []
        self.worker = None
        self.fix_queue = []
        self.fix_total_jobs = 0
        self.fix_done_jobs = 0
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6,6,6,6); root.setSpacing(8)

        # ── LEFT: INPUT AND SCAN CONTROLS ─────────────────────────────
        left = QWidget(); left.setFixedWidth(315)
        ll = QVBoxLayout(left); ll.setContentsMargins(0,0,0,0); ll.setSpacing(6)

        grp_l = QGroupBox("Input Layers"); grp_l.setStyleSheet(GRP_STYLE)
        gl = QVBoxLayout(grp_l)
        sel_row = QHBoxLayout()
        self.btn_all  = QPushButton("Select All");  self.btn_all.setFixedHeight(24)
        self.btn_none = QPushButton("Clear");        self.btn_none.setFixedHeight(24)
        sel_row.addWidget(self.btn_all); sel_row.addWidget(self.btn_none)
        gl.addLayout(sel_row)
        self.layer_list = QListWidget()
        self.layer_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.layer_list.setAlternatingRowColors(True)
        self._fill_layers()
        gl.addWidget(self.layer_list)

        self.layer_count_label = QLabel("Selected layers: 0 / 0")
        self.layer_count_label.setStyleSheet("color:#455a64; font-size:11px;")
        gl.addWidget(self.layer_count_label)
        self._update_layer_count_label()

        ll.addWidget(grp_l, stretch=1)

        self.run_btn    = QPushButton("Scan Layers"); self.run_btn.setFixedHeight(32); self.run_btn.setStyleSheet(BTN_RUN)
        self.cancel_btn = QPushButton("Cancel"); self.cancel_btn.setFixedHeight(32); self.cancel_btn.setStyleSheet(BTN_CANCEL); self.cancel_btn.setEnabled(False)
        self.clear_btn  = QPushButton("Clear"); self.clear_btn.setFixedHeight(32); self.clear_btn.setStyleSheet(BTN_CLEAR)
        ll.addWidget(self.run_btn)
        r1 = QHBoxLayout(); r1.addWidget(self.cancel_btn); r1.addWidget(self.clear_btn); ll.addLayout(r1)

        self.progress = make_progress(); ll.addWidget(self.progress)
        ll.addStretch()

        # ── RIGHT: ERROR VIEWER, REPAIR PANEL, LOG ────────────────────
        right = QWidget(); rl = QVBoxLayout(right)
        rl.setContentsMargins(0,0,0,0); rl.setSpacing(6)

        self.summary = QLabel("No scanned layers. Select input layers on the left and click Scan Layers.")
        self.summary.setStyleSheet("font-size:13px; font-weight:600; color:#37474f;")
        rl.addWidget(self.summary)

        self.table = QTableWidget(); self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["☐", "Layer", "Feature ID", "Error Type", "Layer Geom", "Feature Geom"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self._updating_error_checks = False
        self.table.horizontalHeader().sectionClicked.connect(self._handle_error_header_clicked)
        self.table.itemChanged.connect(self._handle_error_item_changed)
        rl.addWidget(self.table, stretch=1)

        # Repair panel is intentionally placed below the viewer so the workflow is:
        # Scan -> Review Issues -> Choose Repair Type -> Repair Selected Features.
        self.repair_group = QGroupBox("Geometry Repair"); self.repair_group.setStyleSheet(GRP_STYLE)
        gf = QVBoxLayout(self.repair_group)
        # Extra top margin keeps the "Fix Type" label clearly inside the Geometry Repair panel,
        # not visually sitting on the QGroupBox border/title line.
        gf.setContentsMargins(10, 24, 10, 10)
        gf.setSpacing(7)

        fix_type_label = QLabel("Fix Type")
        fix_type_label.setStyleSheet("font-weight:600; padding-top:2px; padding-bottom:2px;")
        gf.addWidget(fix_type_label)

        self.radio_polygon  = QRadioButton("Invalid / Wrong-type Geometry Fix")
        self.radio_null     = QRadioButton("Null / Empty / Missing Fix")
        self.radio_polygon.setChecked(True)
        self.mode_group = QButtonGroup()
        self.mode_group.addButton(self.radio_polygon, 0)
        self.mode_group.addButton(self.radio_null, 1)

        radio_container = QWidget()
        radio_layout = QVBoxLayout(radio_container)
        radio_layout.setContentsMargins(12, 0, 0, 0)
        radio_layout.setSpacing(6)
        radio_layout.addWidget(self.radio_polygon)
        radio_layout.addWidget(self.radio_null)
        gf.addWidget(radio_container)


        self.fix_btn = QPushButton("Repair Selected Features")
        self.fix_btn.setFixedHeight(32); self.fix_btn.setStyleSheet(BTN_EXPORT)
        self.fix_btn.setEnabled(False)
        gf.addWidget(self.fix_btn)
        self.repair_group.setEnabled(False)
        rl.addWidget(self.repair_group)

        rl.addWidget(QLabel("Log"))
        self.log_box = QTextEdit(); self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet(LOG_STYLE); self.log_box.setFixedHeight(150)
        rl.addWidget(self.log_box)

        root.addWidget(left); root.addWidget(right, stretch=1)

        self.run_btn.clicked.connect(self._run)
        self.cancel_btn.clicked.connect(self._cancel)
        self.clear_btn.clicked.connect(self._clear)
        self.btn_all.clicked.connect(self.layer_list.selectAll)
        self.btn_none.clicked.connect(self.layer_list.clearSelection)
        self.layer_list.itemSelectionChanged.connect(self._update_layer_count_label)

        # Keep the input layer viewer updated when polygon layers are added or removed in QGIS.
        QgsProject.instance().layersAdded.connect(self._refresh_layers_keep_selection)
        QgsProject.instance().layersRemoved.connect(self._refresh_layers_keep_selection)

        self.fix_btn.clicked.connect(self._fix_checked_errors)
        self.mode_group.buttonToggled.connect(lambda *_: self._apply_fix_type_filter())
        self.table.cellDoubleClicked.connect(self._zoom)

    def _fill_layers(self, keep_selected_ids=None):
        """Refresh the input layer list from the current QGIS project.

        keep_selected_ids preserves the user's current layer selection when QGIS
        layers are added or removed. This makes the layer viewer feel live while
        avoiding accidental loss of selected inputs.
        """
        keep_selected_ids = set(keep_selected_ids or [])
        self.layer_list.blockSignals(True)
        self.layer_list.clear(); self._lmap = {}
        for lid, lyr in get_polygon_layers().items():
            item = QListWidgetItem(lyr.name()); item.setData(Qt.UserRole, lid)
            self.layer_list.addItem(item); self._lmap[lid] = lyr
            if lid in keep_selected_ids:
                item.setSelected(True)
        self.layer_list.blockSignals(False)

    def _selected_layer_ids(self):
        return [i.data(Qt.UserRole) for i in self.layer_list.selectedItems()]

    def _selected(self):
        return [self._lmap[i.data(Qt.UserRole)] for i in self.layer_list.selectedItems()
                if i.data(Qt.UserRole) in self._lmap]

    def _update_layer_count_label(self):
        if not hasattr(self, "layer_count_label"):
            return
        selected = len(self.layer_list.selectedItems())
        total = self.layer_list.count()
        self.layer_count_label.setText(f"Selected layers: {selected} / {total}")

    def _refresh_layers_keep_selection(self, *args):
        selected_ids = self._selected_layer_ids() if hasattr(self, "layer_list") else []
        self._fill_layers(keep_selected_ids=selected_ids)
        self._update_layer_count_label()

    def _log(self, msg): self.log_box.append(msg)

    def _run(self):
        layers = self._selected()
        if not layers:
            return QMessageBox.warning(self, "No Layers", "Select at least one polygon layer.")
        # Version 1.0: always run all validation checks automatically.
        checks = {"null": True, "empty": True, "wrong": True, "invalid": True}
        self.issues = []; self.table.setRowCount(0); self._update_error_header_checkbox(); self.log_box.clear()
        self.progress.setValue(0); self.summary.setText("Scanning geometry errors...")
        self.fix_btn.setEnabled(False); self.repair_group.setEnabled(False)
        self.run_btn.setEnabled(False); self.cancel_btn.setEnabled(True)
        self.worker = CheckWorker(layers, checks)
        self.worker.log.connect(self._log)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.issue_found.connect(self._add_row)
        self.worker.finished.connect(self._done)
        self.worker.start()

    def _cancel(self):
        if self.worker: self.worker.cancel(); self._log("Cancelled.")
        self.run_btn.setEnabled(True); self.cancel_btn.setEnabled(False); self.fix_btn.setEnabled(bool(self.issues)); self.repair_group.setEnabled(bool(self.issues))

    def _done(self, total):
        self.run_btn.setEnabled(True); self.cancel_btn.setEnabled(False)
        self.fix_btn.setEnabled(total > 0); self.repair_group.setEnabled(total > 0)
        self.summary.setText(f"Scan complete - {total} error(s) found. Check errors in the viewer panel, then choose Fix Type and click Repair Selected Features.")
        self._apply_fix_type_filter()

    def _add_row(self, data):
        self.issues.append(data)
        row = self.table.rowCount(); self.table.insertRow(row)
        issue = data["issue_type"]
        self._updating_error_checks = True
        chk = QTableWidgetItem("")
        chk.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
        chk.setCheckState(Qt.Unchecked)
        self.table.setItem(row, 0, chk)
        self.table.setItem(row, 1, QTableWidgetItem(data["layer_name"]))
        self.table.setItem(row, 2, QTableWidgetItem(str(data["feature_id"])))
        self.table.setItem(row, 3, colored_item(issue, issue))
        self.table.setItem(row, 4, QTableWidgetItem(data["layer_geom_type"]))
        self.table.setItem(row, 5, QTableWidgetItem(data["feature_geom_type"]))
        self._updating_error_checks = False
        self._apply_fix_type_filter()

    def _allowed_issues_for_current_fix_type(self):
        mode = self.mode_group.checkedId()
        if mode == 0:
            return {"Invalid Geometry", "Wrong-type Geometry"}
        return {"Null Geometry", "Empty/Missing Geometry"}

    def _is_row_compatible_with_current_fix_type(self, row):
        return row < len(self.issues) and self.issues[row]["issue_type"] in self._allowed_issues_for_current_fix_type()

    def _apply_fix_type_filter(self):
        """Visually grey-out and disable error rows that do not match the selected fixer."""
        allowed = self._allowed_issues_for_current_fix_type()
        mode_name = (
            "Invalid / Wrong-type Geometry Fix"
            if self.mode_group.checkedId() == 0
            else "Null / Empty / Missing Fix"
        )
        grey_bg = QColor(235, 235, 235)
        grey_fg = QColor(140, 140, 140)

        compatible_count = 0
        checked_compatible_count = 0

        for row in range(self.table.rowCount()):
            issue = self.issues[row]["issue_type"] if row < len(self.issues) else ""
            compatible = issue in allowed
            chk = self.table.item(row, 0)

            if compatible:
                compatible_count += 1
                if chk:
                    chk.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
                    chk.setToolTip(f"Compatible with {mode_name}.")
                    if chk.checkState() == Qt.Checked:
                        checked_compatible_count += 1
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    if not item:
                        continue
                    item.setForeground(QColor(0, 0, 0))
                    item.setToolTip(f"Compatible with {mode_name}.")
                    item.setBackground(QColor(255, 255, 255))
            else:
                if chk:
                    chk.setCheckState(Qt.Unchecked)
                    chk.setFlags(Qt.ItemIsSelectable)
                    chk.setToolTip(f"Disabled: {issue} is not handled by {mode_name}.")
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    if not item:
                        continue
                    item.setBackground(grey_bg)
                    item.setForeground(grey_fg)
                    item.setToolTip(f"Disabled: {issue} is not handled by {mode_name}.")

        self._update_error_header_checkbox()
        self.fix_btn.setEnabled(bool(self.issues) and compatible_count > 0)
        if self.issues:
            self.summary.setText(
                f"Fix Type active: {mode_name} — {compatible_count} compatible error(s), incompatible rows are greyed out."
            )

    def _compatible_error_rows(self):
        return [
            row for row in range(self.table.rowCount())
            if self._is_row_compatible_with_current_fix_type(row)
        ]

    def _set_error_rows_checked(self, checked):
        self._updating_error_checks = True
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if not item:
                continue
            if self._is_row_compatible_with_current_fix_type(row):
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            else:
                item.setCheckState(Qt.Unchecked)
        self._updating_error_checks = False
        self._update_error_header_checkbox()

    def _update_error_header_checkbox(self):
        if not hasattr(self, "table"):
            return
        compatible_rows = self._compatible_error_rows()
        if not compatible_rows:
            self.table.setHorizontalHeaderItem(0, QTableWidgetItem("☐"))
            return
        checked_rows = [
            row for row in compatible_rows
            if self.table.item(row, 0) and self.table.item(row, 0).checkState() == Qt.Checked
        ]
        if len(checked_rows) == len(compatible_rows):
            label = "☑"
        elif checked_rows:
            label = "◩"
        else:
            label = "☐"
        item = QTableWidgetItem(label)
        item.setToolTip("Click to select or clear all compatible errors for the current Fix Type.")
        self.table.setHorizontalHeaderItem(0, item)

    def _handle_error_header_clicked(self, logical_index):
        if logical_index != 0 or not self.issues:
            return
        compatible_rows = self._compatible_error_rows()
        if not compatible_rows:
            return
        all_checked = all(
            self.table.item(row, 0) and self.table.item(row, 0).checkState() == Qt.Checked
            for row in compatible_rows
        )
        self._set_error_rows_checked(not all_checked)

    def _handle_error_item_changed(self, item):
        if self._updating_error_checks:
            return
        if item and item.column() == 0:
            self._update_error_header_checkbox()

    def _checked_issue_rows(self):
        rows = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.Checked and row < len(self.issues):
                rows.append(row)
        if not rows:
            # Convenience: if user selected table rows but did not tick boxes, use highlighted rows.
            rows = sorted({
                i.row() for i in self.table.selectedIndexes()
                if i.row() < len(self.issues) and self._is_row_compatible_with_current_fix_type(i.row())
            })
        else:
            rows = [r for r in rows if self._is_row_compatible_with_current_fix_type(r)]
        return rows

    #DYNAMIC CHANGING OF FIX TYPE: only apply the fix to checked rows that are compatible with the currently selected fix type.
    def _fix_checked_errors(self):
        rows = self._checked_issue_rows()
        if not rows:
            return QMessageBox.warning(self, "No Errors Selected", "Check at least one error in the viewer panel, or highlight rows in the table.")

        mode = self.mode_group.checkedId()
        allowed = {0: {"Invalid Geometry", "Wrong-type Geometry"}, 1: {"Null Geometry", "Empty/Missing Geometry"}}[mode]
        mode_name = "Invalid / Wrong-type Geometry Fix" if mode == 0 else "Null / Empty / Missing Fix"

        by_layer = {}
        skipped = []
        for row in rows:
            d = self.issues[row]
            if d["issue_type"] not in allowed:
                skipped.append(f"FID {d['feature_id']} ({d['issue_type']})")
                continue
            lid = d["layer"].id()
            by_layer.setdefault(lid, {"layer": d["layer"], "ids": set()})["ids"].add(d["feature_id"])

        if not by_layer:
            return QMessageBox.warning(
                self,
                "No Compatible Errors",
                f"The checked rows do not match the selected Fix Type: {mode_name}."
            )

        if skipped:
            self._log("Skipped incompatible checked rows for this fix type:")
            for msg in skipped[:20]: self._log("  - " + msg)
            if len(skipped) > 20: self._log(f"  ...and {len(skipped)-20} more")

        self.fix_queue = []
        for item in by_layer.values():
            self.fix_queue.append((mode, item["layer"], sorted(item["ids"])))
        self.fix_total_jobs = len(self.fix_queue)
        self.fix_done_jobs = 0
        self.run_btn.setEnabled(False); self.fix_btn.setEnabled(False); self.repair_group.setEnabled(False); self.cancel_btn.setEnabled(True)
        self.progress.setValue(0)
        self.summary.setText(f"Running {mode_name}…")
        self._start_next_fix_job()

    def _start_next_fix_job(self):
        if not self.fix_queue:
            self.run_btn.setEnabled(True); self.fix_btn.setEnabled(bool(self.issues)); self.repair_group.setEnabled(bool(self.issues)); self.cancel_btn.setEnabled(False)
            self.progress.setValue(100)
            self.summary.setText(f"Fixing complete - temporary output layer(s) created: {self.fix_done_jobs}/{self.fix_total_jobs}")
            self._apply_fix_type_filter()
            return

        mode, layer, ids = self.fix_queue.pop(0)
        self._log(f"\n=== Fix job {self.fix_done_jobs + 1}/{self.fix_total_jobs}: {layer.name()} | selected error features: {len(ids)} ===")
        if mode == 0:
            self.worker = PolygonFixerWorker(layer, True, selected_ids=ids)
            self.worker.finished.connect(self._done_fixer)
        else:
            self.worker = NullFixerWorker(layer, True, selected_ids=ids)
            self.worker.finished.connect(self._done_null)
        self.worker.log.connect(self._log)
        self.worker.progress.connect(self._progress_fix_job)
        self.worker.start()

    def _progress_fix_job(self, value):
        if self.fix_total_jobs <= 1:
            self.progress.setValue(value)
        else:
            base = int((self.fix_done_jobs / self.fix_total_jobs) * 100)
            span = int(value / self.fix_total_jobs)
            self.progress.setValue(min(100, base + span))

    def _done_fixer(self, fixed, copied):
        self.fix_done_jobs += 1
        self._log(f"Output created. Fixed: {fixed}   Copied: {copied}")
        self._start_next_fix_job()

    def _done_null(self, recovered, copied, manual):
        self.fix_done_jobs += 1
        self._log(f"Output created. Recovered: {recovered}   Manual review: {manual}   Copied: {copied}")
        self._start_next_fix_job()

    def _zoom(self, row, _):
        if row >= len(self.issues): return
        d = self.issues[row]
        try:
            feat = next(d["layer"].getFeatures(QgsFeatureRequest(d["feature_id"])))
            g = feat.geometry()
            if g and not g.isEmpty():
                bb = g.boundingBox(); bb.scale(1.5)
                iface.mapCanvas().setExtent(bb); iface.mapCanvas().refresh()
                self._log(f"Zoomed: FID {d['feature_id']} in {d['layer_name']}")
            else:
                self._log(f"Cannot zoom: FID {d['feature_id']} has Null/Empty geometry.")
        except Exception as e:
            self._log(f"Zoom failed: {e}")

    def _clear(self):
        self.issues = []; self.table.setRowCount(0); self._update_error_header_checkbox(); self.log_box.clear()
        self.progress.setValue(0); self.summary.setText("Results cleared.")
        self.fix_btn.setEnabled(False); self.repair_group.setEnabled(False)


# =============================================================================
# TAB 2 — GEOMETRY FIXER WORKERS
# =============================================================================

class PolygonFixerWorker(QThread):
    """Mirrors 2_geometry_fixer.py logic."""
    log      = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(int, int)   # fixed, copied

    def __init__(self, layer, selected_only, selected_ids=None):
        super().__init__()
        self.layer = layer; self.selected_only = selected_only; self.forced_selected_ids = set(selected_ids or []); self._cancel = False

    def cancel(self): self._cancel = True

    def _clean(self, geom):
        if geom is None or geom.isEmpty(): return None
        g = QgsGeometry(geom)
        try:
            if not g.isGeosValid(): g = g.makeValid()
        except: pass
        if QgsWkbTypes.geometryType(g.wkbType()) == QgsWkbTypes.PolygonGeometry: return g
        try:
            tmp = QgsGeometry(g)
            if tmp.convertGeometryCollectionToSubclass(QgsWkbTypes.PolygonGeometry): return tmp
        except: pass
        return None

    def _force_single(self, geom):
        if geom is None or geom.isEmpty(): return None
        g = QgsGeometry(geom)
        if not g.isMultipart(): return g
        parts = [p for p in g.asGeometryCollection()
                 if p and not p.isEmpty()
                 and QgsWkbTypes.geometryType(p.wkbType()) == QgsWkbTypes.PolygonGeometry]
        return max(parts, key=lambda x: x.area()) if parts else None

    def _is_valid_polygon_geom(self, geom):
        if geom is None or geom.isEmpty():
            return False
        try:
            if QgsWkbTypes.geometryType(geom.wkbType()) != QgsWkbTypes.PolygonGeometry:
                return False
        except Exception:
            return False
        try:
            return geom.isGeosValid()
        except Exception:
            return True

    def _fit_output_wkb(self, geom, output_wkb):
        if geom is None or geom.isEmpty():
            return None
        g = QgsGeometry(geom)
        SINGLE = (QgsWkbTypes.Polygon, QgsWkbTypes.Polygon25D,
                  QgsWkbTypes.PolygonZ, QgsWkbTypes.PolygonM, QgsWkbTypes.PolygonZM)
        if output_wkb in SINGLE or QgsWkbTypes.flatType(output_wkb) == QgsWkbTypes.Polygon:
            g = self._force_single(g)
        else:
            try:
                if QgsWkbTypes.isMultiType(output_wkb) and not g.isMultipart():
                    g.convertToMultiType()
            except Exception:
                pass
        return g

    def _clean_try_makevalid_buffer(self, geom, output_wkb):
        if geom is None or geom.isEmpty():
            return None
        g = self._clean(geom)
        if g is None or g.isEmpty():
            return None
        try:
            if not g.isGeosValid():
                mg = g.makeValid()
                if mg and not mg.isEmpty():
                    g = self._clean(mg)
        except Exception:
            pass
        try:
            if g is not None and not g.isEmpty() and not g.isGeosValid():
                bg = g.buffer(0, 8)
                if bg and not bg.isEmpty():
                    g = self._clean(bg)
        except Exception:
            pass
        g = self._fit_output_wkb(g, output_wkb)
        if self._is_valid_polygon_geom(g):
            return g
        return None

    def _repair_micro_self_intersection_spike(self, geom, output_wkb):
        """Fallback for very small self-intersection spikes/loops on polygon edges.

        Some LGU/PSA boundaries have a tiny folded edge where two vertices cross
        almost at the same location. GEOS makeValid or Polygonize can keep the
        folded edge. This fallback tries conservative cleanup passes only when
        the normal 2_geometry_fixer.py workflow still returns invalid geometry.
        """
        if geom is None or geom.isEmpty():
            return None

        base = QgsGeometry(geom)
        try:
            bb = base.boundingBox()
            diag = ((bb.width() ** 2) + (bb.height() ** 2)) ** 0.5
        except Exception:
            diag = 0
        if not diag or diag <= 0:
            diag = 1.0

        # Very small tolerances first, then slightly stronger tolerances.
        # This is intended for the small red spike/loop shown after zooming in.
        tolerances = [diag * f for f in (1e-12, 5e-12, 1e-11, 5e-11, 1e-10, 5e-10,
                                        1e-9, 5e-9, 1e-8, 5e-8, 1e-7, 5e-7, 1e-6)]
        tried = []
        for tol in tolerances:
            if tol <= 0:
                continue
            # 1) Remove near-duplicate/fold vertices.
            try:
                g1 = QgsGeometry(base)
                g1.removeDuplicateNodes(tol, True)
                tried.append(g1)
            except Exception:
                pass
            # 2) Snap coordinates to a tiny grid to collapse the folded spike.
            try:
                tried.append(base.snappedToGrid(tol, tol))
            except Exception:
                pass
            # 3) Simplify only as later fallback. Very small tolerance is used.
            try:
                tried.append(base.simplify(tol))
            except Exception:
                pass

            for candidate in tried[-3:]:
                fixed = self._clean_try_makevalid_buffer(candidate, output_wkb)
                if fixed and not fixed.isEmpty():
                    return fixed

        return None

    def _finalize_fixed_geom(self, geom, output_wkb):
        """Final safety pass for the Invalid/Wrong-type fixer.

        Main workflow remains from 2_geometry_fixer.py:
        Polygons to Lines → Polygonize → makeValid/GeometryCollection-to-polygon.
        Extra fallback is only used when the normal result is still invalid,
        especially for tiny edge spikes that still report Self-intersection.
        """
        g = self._clean_try_makevalid_buffer(geom, output_wkb)
        if g and not g.isEmpty():
            return g

        # New fallback for tiny folded boundary spike / self-intersection loop.
        g = self._repair_micro_self_intersection_spike(geom, output_wkb)
        if g and not g.isEmpty():
            return g

        return None




    def _qgis_fix_single_feature_fallback(self, source_layer, source_feat, context, feedback):
        """Last-resort fallback for selected Invalid/Wrong-type features.

        This is only used when the original polygonize/makeValid workflow cannot
        return a valid polygon. It runs QGIS native:fixgeometries on the original
        feature record, then converts the result back to the input layer WKB type.
        """
        try:
            tmp = QgsVectorLayer(
                f"{QgsWkbTypes.displayString(source_layer.wkbType())}?crs={source_layer.crs().authid()}",
                source_layer.name() + "_single_fix_input",
                "memory"
            )
            tmp.dataProvider().addAttributes(source_layer.fields())
            tmp.updateFields()

            tf = QgsFeature(source_layer.fields())
            tf.setAttributes(source_feat.attributes())
            tf.setGeometry(source_feat.geometry())
            ok, _ = tmp.dataProvider().addFeatures([tf])
            tmp.updateExtents()

            if (not ok) or tmp.featureCount() == 0:
                # Wrong-type GeometryCollection may be rejected by a polygon memory layer.
                # Try to extract polygon parts first, then run Fix Geometries.
                extracted = self._clean(source_feat.geometry())
                if extracted is None or extracted.isEmpty():
                    return None
                tmp = QgsVectorLayer(
                    f"{QgsWkbTypes.displayString(source_layer.wkbType())}?crs={source_layer.crs().authid()}",
                    source_layer.name() + "_single_fix_input_extracted",
                    "memory"
                )
                tmp.dataProvider().addAttributes(source_layer.fields())
                tmp.updateFields()
                tf = QgsFeature(source_layer.fields())
                tf.setAttributes(source_feat.attributes())
                tf.setGeometry(extracted)
                ok, _ = tmp.dataProvider().addFeatures([tf])
                tmp.updateExtents()
                if (not ok) or tmp.featureCount() == 0:
                    return None

            res = processing.run(
                "native:fixgeometries",
                {"INPUT": tmp, "METHOD": 1, "OUTPUT": "TEMPORARY_OUTPUT"},
                context=context,
                feedback=feedback,
                is_child_algorithm=False
            )
            fixed_layer = resolve_processing_output_layer(res["OUTPUT"], context)
            if fixed_layer is None or fixed_layer.featureCount() == 0:
                return None

            best = None
            for ff in fixed_layer.getFeatures(QgsFeatureRequest().setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)):
                fg = self._finalize_fixed_geom(ff.geometry(), source_layer.wkbType())
                if fg is None or fg.isEmpty():
                    continue
                try:
                    if fg.isGeosValid():
                        if best is None or fg.area() > best.area():
                            best = fg
                except Exception:
                    if best is None or fg.area() > best.area():
                        best = fg
            return best
        except Exception:
            return None

    def _make_selected_input_layer(self, source_layer, selected_ids):
        """Create a temporary in-memory polygon layer from the chosen FIDs.

        This avoids the QGIS Processing error where a layer ID coming from the
        viewer table is not found by the child processing context. The geometry
        repair workflow is still the same as 2_geometry_fixer.py: the chosen
        features are the INPUT for Polygons to Lines, then Polygonize.
        """
        tmp = QgsVectorLayer(
            f"{QgsWkbTypes.displayString(source_layer.wkbType())}?crs={source_layer.crs().authid()}",
            source_layer.name() + "_selected_error_input",
            "memory"
        )
        tmp.dataProvider().addAttributes(source_layer.fields())
        tmp.updateFields()

        req = QgsFeatureRequest().setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)
        req.setFilterFids(list(selected_ids))
        out_feats = []
        for feat in source_layer.getFeatures(req):
            out = QgsFeature(source_layer.fields())
            out.setAttributes(feat.attributes())
            out.setGeometry(feat.geometry())
            out_feats.append(out)

        tmp.dataProvider().addFeatures(out_feats)
        tmp.updateExtents()
        return tmp

    def run(self):
        layer = self.layer
        ctx = QgsProcessingContext(); ctx.setProject(QgsProject.instance()); fb = QgsProcessingFeedback()
        SINGLE = (QgsWkbTypes.Polygon, QgsWkbTypes.Polygon25D,
                  QgsWkbTypes.PolygonZ, QgsWkbTypes.PolygonM, QgsWkbTypes.PolygonZM)

        old_selection = list(layer.selectedFeatureIds())

        if self.selected_only:
            sel_ids = list(self.forced_selected_ids) if self.forced_selected_ids else list(layer.selectedFeatureIds())
            if not sel_ids:
                self.log.emit("No features selected."); self.finished.emit(0, 0); return

            # IMPORTANT:
            # Do NOT rebuild the checked rows into a new memory polygon layer here.
            # Wrong-type errors can be GeometryCollection features inside a polygon layer,
            # and a polygon memory provider may reject those geometries, causing
            # 'selected error input layer has no features'.
            # Instead, search the FIDs in the ORIGINAL layer and temporarily select them,
            # exactly like the original 2_geometry_fixer.py selected-features workflow.
            found_ids = []
            req_check = QgsFeatureRequest().setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)
            wanted = set(sel_ids)
            for f in layer.getFeatures(req_check):
                if f.id() in wanted:
                    found_ids.append(f.id())

            if not found_ids:
                self.log.emit("Selected error FID(s) were not found in the original layer.")
                self.finished.emit(0, 0); return

            sel_ids = found_ids
            layer.selectByIds(sel_ids)
            src = QgsProcessingFeatureSourceDefinition(layer.id(), selectedFeaturesOnly=True)
        else:
            req = QgsFeatureRequest().setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)
            sel_ids = [f.id() for f in layer.getFeatures(req)]
            src = layer

        self.log.emit(f"Features to process: {len(sel_ids)}")
        self.log.emit("Selected feature ID(s): " + ", ".join(str(fid) for fid in sel_ids))
        self.log.emit("Preparing selected feature boundaries…"); self.progress.emit(5)

        try:
            lr = processing.run("native:polygonstolines", {"INPUT":src,"OUTPUT":"TEMPORARY_OUTPUT"},
                                context=ctx, feedback=fb, is_child_algorithm=False)
            ll = resolve_processing_output_layer(lr["OUTPUT"], ctx)
        except Exception as e:
            if self.selected_only:
                layer.selectByIds(old_selection)
            self.log.emit(f"Preparing selected feature boundaries failed: {e}"); self.finished.emit(0, 0); return

        if ll is None or ll.featureCount() == 0:
            if self.selected_only:
                layer.selectByIds(old_selection)
            self.log.emit("No repair boundary was created."); self.finished.emit(0, 0); return

        self.log.emit("Building repair candidates…"); self.progress.emit(25)
        try:
            pr = processing.run("native:polygonize", {"INPUT":ll,"KEEP_FIELDS":False,"OUTPUT":"TEMPORARY_OUTPUT"},
                                context=ctx, feedback=fb, is_child_algorithm=False)
            pl = resolve_processing_output_layer(pr["OUTPUT"], ctx)
        except Exception as e:
            if self.selected_only:
                layer.selectByIds(old_selection)
            self.log.emit(f"Building repair candidates failed: {e}"); self.finished.emit(0, 0); return

        if pl is None or pl.featureCount() == 0:
            if self.selected_only:
                layer.selectByIds(old_selection)
            self.log.emit("No repair candidate was created."); self.finished.emit(0, 0); return

        self.log.emit(f"Repair candidates created: {pl.featureCount()}")
        self.log.emit("Analyzing repair candidates…"); self.progress.emit(45)

        p_feats = []; p_idx = QgsSpatialIndex()
        for pf in pl.getFeatures():
            cg = self._clean(pf.geometry())
            if cg is None or cg.isEmpty(): continue
            pf.setGeometry(cg); p_feats.append(pf); p_idx.addFeature(pf)
        p_lookup = {f.id(): f for f in p_feats}

        if not p_feats:
            if self.selected_only:
                layer.selectByIds(old_selection)
            self.log.emit("No valid polygonized geometry."); self.finished.emit(0, 0); return

        self.log.emit("Creating temporary output layer…"); self.progress.emit(60)

        out_uri = QgsWkbTypes.displayString(layer.wkbType()) + f"?crs={layer.crs().authid()}"
        out_lyr = QgsVectorLayer(out_uri, layer.name() + "_FIXED", "memory")
        out_lyr.dataProvider().addAttributes(layer.fields()); out_lyr.updateFields()
        out_lyr.startEditing()

        fixed = 0; copied = 0; sel_set = set(sel_ids); total = layer.featureCount()
        req = QgsFeatureRequest().setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)

        for i, feat in enumerate(layer.getFeatures(req)):
            if self._cancel: break
            if total: self.progress.emit(60 + int((i / total) * 35))
            out = QgsFeature(out_lyr.fields()); out.setAttributes(feat.attributes())
            orig = feat.geometry()

            if feat.id() not in sel_set:
                out.setGeometry(orig); out_lyr.addFeature(out); copied += 1; continue

            co = self._clean(orig)
            if co is None or co.isEmpty():
                try: co = self._clean(orig.makeValid())
                except: co = None

            if co is None or co.isEmpty():
                qfix = self._qgis_fix_single_feature_fallback(layer, feat, ctx, fb)
                if qfix and not qfix.isEmpty():
                    out.setGeometry(qfix); out_lyr.addFeature(out); fixed += 1
                    self.log.emit(f"   FID {feat.id()} repaired using QGIS Fix Geometries fallback.")
                    continue
                out.setGeometry(orig); out_lyr.addFeature(out); copied += 1
                self.log.emit(f"   FID {feat.id()} couldn't be cleaned — copied original."); continue

            cands = []
            for cid in p_idx.intersects(co.boundingBox()):
                pf = p_lookup.get(cid)
                if not pf: continue
                pg = pf.geometry()
                if pg is None or pg.isEmpty(): continue
                try:
                    if pg.intersects(co):
                        inter = pg.intersection(co)
                        if inter and not inter.isEmpty() and inter.area() > 0: cands.append(pg)
                except:
                    if pg.boundingBox().intersects(co.boundingBox()): cands.append(pg)

            if cands:
                ng = QgsGeometry.unaryUnion(cands)
                ng = self._finalize_fixed_geom(ng, layer.wkbType())
                if ng and not ng.isEmpty():
                    out.setGeometry(ng); fixed += 1
                else:
                    # Fallback: use the cleaned original geometry instead of copying the invalid original.
                    fallback = self._finalize_fixed_geom(co, layer.wkbType())
                    if fallback and not fallback.isEmpty():
                        out.setGeometry(fallback); fixed += 1
                        self.log.emit(f"   FID {feat.id()} polygonized union still invalid — used makeValid fallback.")
                    else:
                        qfix = self._qgis_fix_single_feature_fallback(layer, feat, ctx, fb)
                        if qfix and not qfix.isEmpty():
                            out.setGeometry(qfix); fixed += 1
                            self.log.emit(f"   FID {feat.id()} repaired using QGIS Fix Geometries fallback.")
                        else:
                            out.setGeometry(orig); copied += 1
            else:
                # For stubborn self-intersections, polygonize may produce no matching face.
                # Do not immediately copy the bad geometry; first try the cleaned original.
                fallback = self._finalize_fixed_geom(co, layer.wkbType())
                if fallback and not fallback.isEmpty():
                    out.setGeometry(fallback); fixed += 1
                    self.log.emit(f"   FID {feat.id()} no polygonized match — used makeValid fallback.")
                else:
                    qfix = self._qgis_fix_single_feature_fallback(layer, feat, ctx, fb)
                    if qfix and not qfix.isEmpty():
                        out.setGeometry(qfix); fixed += 1
                        self.log.emit(f"   FID {feat.id()} repaired using QGIS Fix Geometries fallback.")
                    else:
                        out.setGeometry(orig); copied += 1
                        self.log.emit(f"   FID {feat.id()} no polygonized match — copied original.")

            # Final selected-feature guard: do not knowingly write an invalid selected geometry
            # when a QGIS Fix Geometries fallback can repair it.
            if feat.id() in sel_set:
                try:
                    og = out.geometry()
                    if og and not og.isEmpty() and not og.isGeosValid():
                        spikefix = self._repair_micro_self_intersection_spike(og, layer.wkbType())
                        if spikefix and not spikefix.isEmpty() and spikefix.isGeosValid():
                            out.setGeometry(spikefix)
                            self.log.emit(f"   FID {feat.id()} final validation repaired by micro-spike/self-intersection fallback.")
                        else:
                            qfix = self._qgis_fix_single_feature_fallback(layer, feat, ctx, fb)
                            if qfix and not qfix.isEmpty() and qfix.isGeosValid():
                                out.setGeometry(qfix)
                                self.log.emit(f"   FID {feat.id()} final validation repaired by QGIS Fix Geometries fallback.")
                except Exception:
                    pass

            out_lyr.addFeature(out)

        out_lyr.commitChanges(); out_lyr.updateExtents()
        QgsProject.instance().addMapLayer(out_lyr)
        if self.selected_only:
            layer.selectByIds(old_selection)
        self.progress.emit(100)
        self.log.emit(f"\nFinished.Fixed: {fixed}   Copied: {copied}")
        self.finished.emit(fixed, copied)


class NullFixerWorker(QThread):
    """Mirrors 3_null_and_missing_fixer.py logic."""
    log      = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(int, int, int)   # recovered, copied, manual

    def __init__(self, layer, selected_only, selected_ids=None):
        super().__init__()
        self.layer = layer; self.selected_only = selected_only; self.forced_selected_ids = set(selected_ids or []); self._cancel = False

    def cancel(self): self._cancel = True

    def _clean(self, geom):
        if geom is None or geom.isEmpty(): return None
        g = QgsGeometry(geom)
        try:
            if not g.isGeosValid(): g = g.makeValid()
        except: pass
        if QgsWkbTypes.geometryType(g.wkbType()) == QgsWkbTypes.PolygonGeometry: return g
        try:
            tmp = QgsGeometry(g)
            if tmp.convertGeometryCollectionToSubclass(QgsWkbTypes.PolygonGeometry): return tmp
        except: pass
        return None

    def _force_single(self, geom):
        if geom is None or geom.isEmpty(): return None
        g = QgsGeometry(geom)
        if not g.isMultipart(): return g
        parts = [p for p in g.asGeometryCollection()
                 if p and not p.isEmpty()
                 and QgsWkbTypes.geometryType(p.wkbType()) == QgsWkbTypes.PolygonGeometry]
        return max(parts, key=lambda x: x.area()) if parts else None

    def _match_type(self, geom, wkb):
        if geom is None or geom.isEmpty(): return None
        g = QgsGeometry(geom)
        SINGLE = (QgsWkbTypes.Polygon, QgsWkbTypes.Polygon25D,
                  QgsWkbTypes.PolygonZ, QgsWkbTypes.PolygonM, QgsWkbTypes.PolygonZM)
        if wkb in SINGLE or QgsWkbTypes.flatType(wkb) == QgsWkbTypes.Polygon:
            return self._force_single(g)
        try:
            if QgsWkbTypes.isMultiType(wkb) and not g.isMultipart():
                g.convertToMultiType()
        except Exception:
            pass
        return g

    def run(self):
        layer = self.layer
        ctx = QgsProcessingContext(); fb = QgsProcessingFeedback()
        sel_ids = set(self.forced_selected_ids) if self.forced_selected_ids else set(layer.selectedFeatureIds())

        if self.selected_only and not sel_ids:
            self.log.emit("No features selected."); self.finished.emit(0, 0, 0); return

        req = QgsFeatureRequest().setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)
        missing_ids = []; valid_feats = []; valid_geoms = []

        self.log.emit("Scanning layer…")
        for feat in layer.getFeatures(req):
            if self._cancel: break
            geom = feat.geometry()
            is_miss = (geom is None or geom.isNull() or geom.isEmpty())
            if self.selected_only:
                if feat.id() in sel_ids and is_miss: missing_ids.append(feat.id())
                elif not is_miss:
                    cg = self._clean(geom)
                    if cg and not cg.isEmpty(): valid_feats.append((feat, cg)); valid_geoms.append(cg)
            else:
                if is_miss: missing_ids.append(feat.id())
                else:
                    cg = self._clean(geom)
                    if cg and not cg.isEmpty(): valid_feats.append((feat, cg)); valid_geoms.append(cg)

        self.log.emit(f"Missing Null/Empty: {len(missing_ids)}")
        if missing_ids:
            self.log.emit("Selected feature ID(s): " + ", ".join(str(fid) for fid in missing_ids))
        self.log.emit(f"Valid surrounding polygons: {len(valid_feats)}")

        if not missing_ids:
            self.log.emit("No Null/Empty features found."); self.finished.emit(0, 0, 0); return
        if not valid_feats:
            self.log.emit("No valid surrounding polygons found."); self.finished.emit(0, 0, 0); return

        self.progress.emit(10)
        valid_lyr = QgsVectorLayer(
            f"{QgsWkbTypes.displayString(layer.wkbType())}?crs={layer.crs().authid()}",
            "_valid_surround", "memory")
        valid_lyr.dataProvider().addAttributes(layer.fields()); valid_lyr.updateFields()
        vf = []
        for feat, cg in valid_feats:
            f = QgsFeature(layer.fields()); f.setAttributes(feat.attributes()); f.setGeometry(cg); vf.append(f)
        valid_lyr.dataProvider().addFeatures(vf); valid_lyr.updateExtents()

        union_geom = QgsGeometry.unaryUnion(valid_geoms); union_geom = self._clean(union_geom)
        if union_geom is None or union_geom.isEmpty():
            self.log.emit("Could not build union coverage."); self.finished.emit(0, 0, 0); return

        self.log.emit("Preparing surrounding boundaries…"); self.progress.emit(20)
        try:
            lr = processing.run("native:polygonstolines", {"INPUT":valid_lyr,"OUTPUT":"TEMPORARY_OUTPUT"},
                                context=ctx, feedback=fb, is_child_algorithm=False)
            ll = resolve_processing_output_layer(lr["OUTPUT"], ctx)
        except Exception as e:
            self.log.emit(f"Preparing selected feature boundaries failed: {e}"); self.finished.emit(0, 0, 0); return

        self.log.emit("Searching for recoverable missing areas…"); self.progress.emit(45)
        try:
            pr = processing.run("native:polygonize", {"INPUT":ll,"KEEP_FIELDS":False,"OUTPUT":"TEMPORARY_OUTPUT"},
                                context=ctx, feedback=fb, is_child_algorithm=False)
            pl = resolve_processing_output_layer(pr["OUTPUT"], ctx)
        except Exception as e:
            self.log.emit(f"Building repair candidates failed: {e}"); self.finished.emit(0, 0, 0); return

        if pl is None or pl.featureCount() == 0:
            self.log.emit("No repair candidate was created."); self.finished.emit(0, 0, 0); return
        self.log.emit(f"Recovery candidates created: {pl.featureCount()}")

        self.log.emit("Evaluating recovery candidates…"); self.progress.emit(65)
        cand_gaps = []
        for pf in pl.getFeatures():
            if self._cancel: break
            pg = self._clean(pf.geometry())
            if pg is None or pg.isEmpty() or pg.area() <= 0: continue
            try:
                inter = pg.intersection(union_geom)
                ia = inter.area() if inter and not inter.isEmpty() else 0.0
            except: ia = 0.0
            ratio = ia / pg.area() if pg.area() > 0 else 1.0
            if ratio < 0.01:
                cand_gaps.append(pg)
                self.log.emit(f"  Gap face: area={pg.area():,.4f}  ratio={ratio:.4f}")

        self.log.emit(f"Recoverable candidate areas: {len(cand_gaps)}"); self.progress.emit(80)

        recover_map = {}; gap_area = None
        method_txt = "Not recovered"; note_txt = ""

        if len(missing_ids) == 1 and len(cand_gaps) == 1:
            sg = self._match_type(cand_gaps[0], layer.wkbType())
            recover_map[missing_ids[0]] = sg; gap_area = sg.area()
            method_txt = "Polygonized missing face"
            note_txt   = "Exactly 1 missing + 1 gap face."
            self.log.emit(" Auto-recovered: 1 missing → 1 gap face.")
        elif len(missing_ids) == 1 and len(cand_gaps) > 1:
            sg = self._match_type(max(cand_gaps, key=lambda g: g.area()), layer.wkbType())
            recover_map[missing_ids[0]] = sg; gap_area = sg.area()
            method_txt = "Largest polygonized face"
            note_txt   = f"1 missing + {len(cand_gaps)} candidates → largest assigned. Review carefully."
            self.log.emit(f"Multiple candidates — assigned largest (area={gap_area:,.4f}).")
        else:
            note_txt = f"Missing: {len(missing_ids)}, candidates: {len(cand_gaps)}. Safe auto-match not possible."
            self.log.emit("Auto-recovery not applied — " + note_txt)

        # Output keeps the same attribute fields as the original layer.
        # Recovery details are written to the log only, so PSO users can export
        # the temporary layer without manually deleting extra fields.
        out_fields = QgsFields()
        for fld in layer.fields(): out_fields.append(fld)

        # Use the flat 2D polygon/multipolygon type for the temporary output layer.
        # This avoids commit errors when the source layer is Z/M but recovered
        # polygonized faces are returned by QGIS as 2D geometries.
        out_wkb = QgsWkbTypes.flatType(layer.wkbType())
        out_lyr = QgsVectorLayer(
            f"{QgsWkbTypes.displayString(out_wkb)}?crs={layer.crs().authid()}",
            layer.name() + "_RECOVERED", "memory")
        out_lyr.dataProvider().addAttributes(out_fields); out_lyr.updateFields(); out_lyr.startEditing()

        recovered = 0; copied = 0; manual = 0; total = layer.featureCount()
        for i, feat in enumerate(layer.getFeatures(req)):
            if self._cancel: break
            if total: self.progress.emit(80 + int((i / total) * 18))
            geom = feat.geometry()
            is_miss = (geom is None or geom.isNull() or geom.isEmpty())
            if self.selected_only and feat.id() not in sel_ids: is_miss = False

            of = QgsFeature(out_fields); attrs = list(feat.attributes())
            if feat.id() in recover_map:
                of.setGeometry(recover_map[feat.id()])
                recovered += 1
                self.log.emit(f"FID {feat.id()}: Recovered. Method: {method_txt}. Note: {note_txt}")
            elif is_miss:
                manual += 1
                self.log.emit(f"FID {feat.id()}: Manual review required. Method: Not recovered. Note: {note_txt}")
            else:
                # Copy non-missing features, but first make sure their geometry is
                # compatible with the temporary polygon output layer. This prevents
                # QGIS commit errors when the original layer also contains
                # GeometryCollection / wrong-type geometries while running the
                # Null / Empty fix.
                copy_geom = self._clean(geom)
                copy_geom = self._match_type(copy_geom, layer.wkbType()) if copy_geom else None
                if copy_geom and not copy_geom.isEmpty():
                    of.setGeometry(copy_geom)
                elif self.selected_only and feat.id() in sel_ids:
                    self.log.emit(f"FID {feat.id()}: Copied without geometry. Note: original geometry is not compatible with polygon output.")
                copied += 1
            of.setAttributes(attrs); out_lyr.addFeature(of)

        if not out_lyr.commitChanges():
            self.log.emit(" Commit warning: " + "; ".join(out_lyr.commitErrors()))
        out_lyr.updateExtents()
        QgsProject.instance().addMapLayer(out_lyr)
        self.progress.emit(100)
        self.log.emit(f"\nFinished.  Recovered: {recovered}   Manual: {manual}   Copied: {copied}")
        self.finished.emit(recovered, copied, manual)


# =============================================================================
# TAB 2 — GEOMETRY FIXER UI  (single tab, mode switcher)
# =============================================================================

# Info text shown in the hint panel per mode
MODE_INFO = {
    0: (
        "Fix Mode: Polygon Fix\n\n"
        " Self-intersections / Bowties\n"
        " Ring self-intersection\n"
        " Duplicate vertices\n"
        " Spikes / slivers\n"
        " GeometryCollection to Polygon\n\n"
        " Null / Empty geometry\n"
        "   → switch to Null / Empty mode"
    ),
    1: (
        "Fix Mode: Null / Empty Fix\n\n"
        " Null Geometry  (record exists)\n"
        " Empty Geometry  (POLYGON EMPTY)\n"
        " Missing / Corrupted geometry\n\n"
        "Requires surrounding valid polygons\n"
        "to reconstruct the missing face.\n\n"
        "Adds recovery_status, recovery_method,\n"
        "recovery_note, candidate_gap_count,\n"
        "selected_gap_area fields to output.\n\n"
        " Deleted features (no record)\n"
        " Point / open LineString geometry"
    ),
}


class GeometryFixerTab(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6); root.setSpacing(8)

        # ── LEFT ──────────────────────────────────────────────────────
        left = QWidget(); left.setFixedWidth(290)
        ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0); ll.setSpacing(8)

        # Fix Mode selector
        mode_grp = QGroupBox("Fix Mode"); mode_grp.setStyleSheet(GRP_STYLE)
        mg = QVBoxLayout(mode_grp)
        self.radio_polygon  = QRadioButton("Polygon Fix  (Invalid / Wrong-type Geometry)")
        self.radio_null     = QRadioButton("Null/Empty Fixer  (Missing Geometry)")
        self.radio_polygon.setChecked(True)
        self.mode_group = QButtonGroup()
        self.mode_group.addButton(self.radio_polygon, 0)
        self.mode_group.addButton(self.radio_null,    1)
        mg.addWidget(self.radio_polygon); mg.addWidget(self.radio_null)
        ll.addWidget(mode_grp)

        # Layer selector
        layer_grp = QGroupBox("Input Layer"); layer_grp.setStyleSheet(GRP_STYLE)
        lg = QVBoxLayout(layer_grp)
        lg.addWidget(QLabel("Polygon layer:"))
        self.layer_combo = QComboBox(); self._fill_combo()
        lg.addWidget(self.layer_combo)
        self.sel_only = QCheckBox("Selected Features Only")
        self.sel_only.setChecked(True)
        lg.addWidget(self.sel_only)
        ll.addWidget(layer_grp)

        # Dynamic hint panel
        hint_grp = QGroupBox("Info"); hint_grp.setStyleSheet(GRP_STYLE)
        hg = QVBoxLayout(hint_grp)
        self.hint_label = QLabel(MODE_INFO[0])
        self.hint_label.setStyleSheet("font-size:11px; color:#37474f;")
        self.hint_label.setWordWrap(True)
        hg.addWidget(self.hint_label)
        ll.addWidget(hint_grp)

        # Buttons
        self.run_btn    = QPushButton("Run");       self.run_btn.setFixedHeight(32);    self.run_btn.setStyleSheet(BTN_RUN)
        self.cancel_btn = QPushButton("Cancel");     self.cancel_btn.setFixedHeight(32); self.cancel_btn.setStyleSheet(BTN_CANCEL); self.cancel_btn.setEnabled(False)
        self.clear_btn  = QPushButton("Clear Log"); self.clear_btn.setFixedHeight(32);  self.clear_btn.setStyleSheet(BTN_CLEAR)
        r1 = QHBoxLayout(); r1.addWidget(self.run_btn); r1.addWidget(self.cancel_btn); ll.addLayout(r1)
        ll.addWidget(self.clear_btn)

        self.progress = make_progress(); ll.addWidget(self.progress)
        ll.addStretch()

        # ── RIGHT ─────────────────────────────────────────────────────
        right = QWidget(); rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(6)

        self.summary = QLabel("Ready.")
        self.summary.setStyleSheet("font-size:13px; font-weight:600; color:#37474f;")
        rl.addWidget(self.summary)

        self.log_box = QTextEdit(); self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet(LOG_STYLE)
        self.log_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        rl.addWidget(self.log_box, stretch=1)

        root.addWidget(left); root.addWidget(right, stretch=1)

        # Signals
        self.run_btn.clicked.connect(self._run)
        self.cancel_btn.clicked.connect(self._cancel)
        self.clear_btn.clicked.connect(lambda: self.log_box.clear())
        self.mode_group.buttonToggled.connect(self._on_mode_changed)

    # ------------------------------------------------------------------
    def _fill_combo(self):
        self.layer_combo.clear(); self._lmap = {}
        for lid, lyr in get_polygon_layers().items():
            self.layer_combo.addItem(lyr.name(), lid); self._lmap[lid] = lyr

    def _current_mode(self):
        return self.mode_group.checkedId()   # 0 = Polygon Fix, 1 = Null/Empty

    def _on_mode_changed(self):
        mode = self._current_mode()
        self.hint_label.setText(MODE_INFO[mode])
        # Adjust checkbox label to match mode
        self.sel_only.setText(
            "Selected Null/Empty Features Only" if mode == 1
            else "Selected Features Only"
        )

    def _log(self, msg): self.log_box.append(msg)

    def _run(self):
        lid = self.layer_combo.currentData()
        if lid is None or lid not in self._lmap:
            return QMessageBox.warning(self, "No Layer", "Select a polygon layer.")
        layer = self._lmap[lid]
        self.log_box.clear(); self.progress.setValue(0); self.summary.setText("Running…")
        self.run_btn.setEnabled(False); self.cancel_btn.setEnabled(True)

        if self._current_mode() == 0:
            self.worker = PolygonFixerWorker(layer, self.sel_only.isChecked())
            self.worker.finished.connect(self._done_fixer)
        else:
            self.worker = NullFixerWorker(layer, self.sel_only.isChecked())
            self.worker.finished.connect(self._done_null)

        self.worker.log.connect(self._log)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.start()

    def _cancel(self):
        if self.worker: self.worker.cancel(); self._log("Cancelled.")
        self.run_btn.setEnabled(True); self.cancel_btn.setEnabled(False)

    def _done_fixer(self, fixed, copied):
        self.run_btn.setEnabled(True); self.cancel_btn.setEnabled(False)
        self.summary.setText(f"Done - Fixed: {fixed}   Copied: {copied}")

    def _done_null(self, recovered, copied, manual):
        self.run_btn.setEnabled(True); self.cancel_btn.setEnabled(False)
        self.summary.setText(f"Done - Recovered: {recovered}   Manual review: {manual}   Copied: {copied}")




# =============================================================================
# TAB 2 — HELP, TOOLTIP, AND DESCRIPTION
# =============================================================================

class HelpInfoTab(QWidget):
    def __init__(self):
        super().__init__()
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        header = QLabel("")
        header.setStyleSheet("font-size:14px; font-weight:700;")
        root.addWidget(header)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setStyleSheet(
            "QTextEdit { background:white; font-size:12px; }"
        )
        self.text.setHtml("""
        <h2>Geometry Validation and Repair Toolkit</h2>
        <p>
        This tool checks polygon layers for geometry errors and creates temporary repaired output layers.
        The original input layer is not edited.
        </p>

        <h3>How to Use</h3>
        <ol>
            <li>Select one or more polygon layers from <b>Input Layers</b>.</li>
            <li>Click <b>Scan Layers</b>.</li>
            <li>Review the detected errors in the table.</li>
            <li>Choose the appropriate <b>Fix Type</b>.</li>
            <li>Compatible error rows will remain available. Incompatible rows will be greyed out.</li>
            <li>Check the errors to repair. You may also click the checkbox in the first column header to select or clear all compatible errors.</li>
            <li>Click <b>Repair Selected Features</b>.</li>
            <li>Review the temporary output layer before saving or replacing any source data.</li>
        </ol>

        <h3>Error Types</h3>
        <table border="1" cellspacing="0" cellpadding="5">
            <tr><th>Error Type</th><th>Description</th><th>Recommended Fix Type</th></tr>
            <tr>
                <td><b>Null Geometry</b></td>
                <td>The feature record exists, but there is no geometry object.</td>
                <td>Null / Empty / Missing Fix</td>
            </tr>
            <tr>
                <td><b>Empty/Missing Geometry</b></td>
                <td>The feature exists, but its geometry has no usable shape or coordinates.</td>
                <td>Null / Empty / Missing Fix</td>
            </tr>
            <tr>
                <td><b>Wrong-type Geometry</b></td>
                <td>The feature geometry does not match the polygon layer type.</td>
                <td>Invalid / Wrong-type Geometry Fix</td>
            </tr>
            <tr>
                <td><b>Invalid Geometry</b></td>
                <td>The polygon has geometry errors such as self-intersection, ring error, spike, or folded edge.</td>
                <td>Invalid / Wrong-type Geometry Fix</td>
            </tr>
        </table>

        <h3>Fix Types</h3>
        <p><b>Invalid / Wrong-type Geometry Fix</b></p>
        <ul>
            <li>Use this for <b>Invalid Geometry</b> and <b>Wrong-type Geometry</b>.</li>
            <li>This is suitable for polygons with self-intersections, spikes, duplicate vertices, folded edges, or recoverable polygon parts.</li>
        </ul>

        <p><b>Null / Empty / Missing Fix</b></p>
        <ul>
            <li>Use this for <b>Null Geometry</b> and <b>Empty/Missing Geometry</b>.</li>
            <li>This is suitable when the feature record still exists and the missing shape can be recovered from surrounding polygons.</li>
        </ul>


        <h3>If One Feature Has Multiple Error Types</h3>
        <p>
        Some features may have more than one geometry problem. For example, a layer may contain invalid or wrong-type geometry together with null, empty, or missing geometry records.
        In this case, follow the repair order below so the output layer stays clean and easier to validate.
        </p>
        <ol>
            <li>Run <b>Invalid / Wrong-type Geometry Fix</b> first.</li>
            <li>Review the temporary output layer created by that fix.</li>
            <li>Scan the temporary output layer again using <b>Scan Layers</b>.</li>
            <li>If the invalid or wrong-type errors are gone, use that temporary output layer as the input for the next step.</li>
            <li>Run <b>Null / Empty / Missing Fix</b> on the temporary output layer.</li>
            <li>Review the new temporary output layer.</li>
            <li>Scan the latest temporary output layer again to check if there are remaining errors.</li>
            <li>If no remaining errors are detected, manually export the latest temporary output layer as the final repaired layer.</li>
        </ol>
        <p>
        Recommended order: <b>Invalid / Wrong-type Geometry Fix first</b>, then <b>Null / Empty / Missing Fix</b> only after the first temporary output layer has been scanned and verified.
        </p>

        <h3>Output Layers</h3>
        <p>
        All repairs create temporary memory layers. The source layer is not modified.
        The temporary output keeps the same original attribute fields so it can be exported more easily.
        Recovery status, method, and notes are shown in the log instead of being added as extra fields.
        </p>

        <h3>Review and Limitations</h3>
        <ul>
            <li>Always visually inspect the temporary output layer.</li>
            <li>Try to run Check Validity again on the temporary output layer.</li>
            <li>Deleted feature records cannot be recovered by this tool.</li>
            <li>Edge polygons cannot be safely reconstructed when the outer boundary is unknown.</li>
            <li>If a missing edge polygon cannot be recovered, return it to the LGU for corrected boundary geometry.</li>
            <li>Some complex errors may still require manual review.</li>
        </ul>

        <h3>Log Information</h3>
        <p>
        The log shows which layer and feature ID were processed, plus the repair result when applicable.
        For Null / Empty / Missing fixes, recovery status, method, and notes are written in the log.
        </p>

        <hr>

        <p align="center">
        <b>Geometry Validation and Repair Toolkit</b><br>
        Version 1.0.2<br>
        Build 2026.06<br><br>
        PSA – Geospatial Management Division<br>
        Project 1MAP
        </p>
        """)
        root.addWidget(self.text, stretch=1)


# =============================================================================
# MAIN DIALOG
# =============================================================================

class GeometryToolkit(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Geometry Validation and Repair Toolkit")
        self.resize(1100, 720)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10); root.setSpacing(6)

        title = QLabel("Geometry Validation and Repair Toolkit")
        title.setStyleSheet("font-size:16px; font-weight:700; padding:2px 0;")
        root.addWidget(title)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setStyleSheet("color:#bdbdbd;")
        root.addWidget(sep)

        tabs = QTabWidget()

        self.checker_tab = CheckerTab()
        self.help_tab = HelpInfoTab()

        tabs.addTab(self.checker_tab, "Geometry Checker and Fixer")
        tabs.addTab(self.help_tab, "Help and Information")

        root.addWidget(tabs, stretch=1)