# =============================================================================
# GEOMETRY VALIDATION AND REPAIR TOOLKIT v1.1.0
# 
#
#
#
#   Tab 1 — Geometry Checker
#
# =============================================================================

from qgis.PyQt.QtCore import QVariant, QThread, QObject, pyqtSignal, Qt, QRect, QEvent
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QTextEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QGroupBox, QCheckBox, QListWidget,
    QListWidgetItem, QAbstractItemView, QWidget, QFrame,
    QTabWidget, QComboBox, QSizePolicy, QRadioButton, QButtonGroup,
    QStackedWidget, QStyle, QStyleOptionButton, QStyledItemDelegate,
    QStyleOptionViewItem, QApplication
)
from qgis.PyQt.QtGui import QColor
from qgis.gui import QgsRubberBand, QgsVertexMarker
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsWkbTypes,
    QgsFeatureRequest, QgsFeature, QgsFields, QgsField,
    QgsFeatureSink, QgsMemoryProviderUtils, QgsGeometry,
    QgsProcessingContext, QgsProcessingFeedback,
    QgsProcessingFeatureSourceDefinition, QgsSpatialIndex,
    QgsProcessingUtils, QgsRectangle, QgsPointXY,
    QgsCoordinateTransform
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


class CheckableHeaderView(QHeaderView):
    """Horizontal header for the issues table whose first section shows a
    real, native-style checkbox indicator (select/clear all auto-fixable
    rows), instead of a unicode glyph drawn as header text. Using the same
    QStyle.CE_CheckBox control the row checkboxes are drawn with keeps size,
    spacing and appearance identical between the header and the rows.
    """

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._check_state = Qt.Unchecked
        self.setSectionsClickable(True)

    def setCheckState(self, state):
        if state != self._check_state:
            self._check_state = state
            self.updateSection(0)

    def paintSection(self, painter, rect, logicalIndex):
        if logicalIndex != 0:
            super().paintSection(painter, rect, logicalIndex)
            return
        painter.save()
        super().paintSection(painter, rect, logicalIndex)
        painter.restore()

        opt = QStyleOptionButton()
        style = self.style()
        w = style.pixelMetric(QStyle.PM_IndicatorWidth, None, self)
        h = style.pixelMetric(QStyle.PM_IndicatorHeight, None, self)
        opt.rect = QRect(rect.x() + (rect.width() - w) // 2,
                          rect.y() + (rect.height() - h) // 2, w, h)
        opt.state = QStyle.State_Enabled
        if self._check_state == Qt.Checked:
            opt.state |= QStyle.State_On
        elif self._check_state == Qt.PartiallyChecked:
            opt.state |= QStyle.State_NoChange
        else:
            opt.state |= QStyle.State_Off
        style.drawControl(QStyle.CE_CheckBox, opt, painter)


class CenteredCheckBoxDelegate(QStyledItemDelegate):
    """Paints and handles the row checkbox in column 0 centered in its cell.

    Qt's default item delegate always draws a check indicator at a fixed
    left inset, ignoring the item's text alignment — that's why setting
    Qt.AlignCenter alone didn't move it. This delegate suppresses the
    built-in (left-aligned) indicator, draws its own centered one with the
    same QStyle.CE_CheckBox control the header checkbox uses, and handles
    mouse clicks against that same centered rect so it stays clickable.
    """

    def _check_rect(self, option):
        style = QApplication.style()
        w = style.pixelMetric(QStyle.PM_IndicatorWidth)
        h = style.pixelMetric(QStyle.PM_IndicatorHeight)
        return QRect(option.rect.x() + (option.rect.width() - w) // 2,
                     option.rect.y() + (option.rect.height() - h) // 2, w, h)

    def paint(self, painter, option, index):
        check_state = index.data(Qt.CheckStateRole)
        if check_state is None:
            super().paint(painter, option, index)
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        style = opt.widget.style() if opt.widget else QApplication.style()
        opt.features &= ~QStyleOptionViewItem.HasCheckIndicator
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        btn = QStyleOptionButton()
        btn.rect = self._check_rect(option)
        btn.state = QStyle.State_Enabled if (index.flags() & Qt.ItemIsEnabled) else QStyle.State_None
        if check_state == Qt.Checked:
            btn.state |= QStyle.State_On
        elif check_state == Qt.PartiallyChecked:
            btn.state |= QStyle.State_NoChange
        else:
            btn.state |= QStyle.State_Off
        style.drawControl(QStyle.CE_CheckBox, btn, painter)

    def editorEvent(self, event, model, option, index):
        if not (index.flags() & Qt.ItemIsUserCheckable) or not (index.flags() & Qt.ItemIsEnabled):
            return False
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if self._check_rect(option).contains(event.pos()):
                cur = index.data(Qt.CheckStateRole)
                new = Qt.Unchecked if cur == Qt.Checked else Qt.Checked
                model.setData(index, new, Qt.CheckStateRole)
                return True
        return False


class LayerCheckDelegate(QStyledItemDelegate):
    """Used for the Input Layers list. Clicking anywhere on a row toggles
    that layer's checkbox — not just the tiny indicator square — so
    checking several layers is a plain, deterministic click each time, with
    no dependency on Ctrl/Shift modifier state (which can be unreliable to
    read across some OS/Qt combinations). Painting is left to the default
    delegate; only the click-to-toggle hit area is widened to the whole row.
    """
    def editorEvent(self, event, model, option, index):
        if not (index.flags() & Qt.ItemIsUserCheckable) or not (index.flags() & Qt.ItemIsEnabled):
            return False
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            cur = index.data(Qt.CheckStateRole)
            new = Qt.Unchecked if cur == Qt.Checked else Qt.Checked
            model.setData(index, new, Qt.CheckStateRole)
            return True
        return False


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


class TopologyError:
    DUPLICATE_GEOMETRY = "Duplicate Geometry"
    SELF_INTERSECTION  = "Self Intersection"
    INVALID_GEOMETRY   = "Invalid Geometry"
    DANGLE             = "Dangle (Loose End)"
    WRONG_TYPE_GEOMETRY = "Wrong-type Geometry"
    NULL_GEOMETRY      = "Null Geometry"

    def __init__(self, error_type, fid, layer_name, geometry, description=""):
        self.error_type  = error_type
        self.fid         = fid
        self.layer_name  = layer_name
        self.geometry    = geometry   # precise error geometry, NOT the whole feature
        self.description = description

    @property
    def bbox(self):
        if self.geometry is None or self.geometry.isNull():
            return None
        bb = self.geometry.boundingBox()
        if self.geometry.type() == QgsWkbTypes.PolygonGeometry:
            bb.scale(1.2)
            return bb
        cx, cy = bb.center().x(), bb.center().y()
        half = max(bb.width(), bb.height()) * 0.5
        min_half = 500.0
        half = max(half, min_half)
        half = min(half, 5000.0)
        return QgsRectangle(cx - half, cy - half, cx + half, cy + half)


# Short, user-facing description of what each error type means — shown as
# the tooltip on issue-table rows (see CheckerTab._apply_fix_type_filter)
# and mirrored in the Help tab's Error Types table.
ERROR_TYPE_DESCRIPTIONS = {
    TopologyError.NULL_GEOMETRY: "The feature record exists, but there is no geometry object.",
    "Empty/Missing Geometry": "The feature exists, but its geometry has no usable shape or coordinates.",
    TopologyError.INVALID_GEOMETRY: "The polygon has geometry errors such as self-intersection, ring error, spike, or folded edge.",
    TopologyError.SELF_INTERSECTION: "The polygon crosses itself.",
    TopologyError.WRONG_TYPE_GEOMETRY: "The feature's geometry type does not match the layer's declared geometry type (e.g. a line or GeometryCollection stored in a polygon layer).",
    TopologyError.DUPLICATE_GEOMETRY: "This feature's geometry is an exact duplicate of another feature's.",
    TopologyError.DANGLE: "A line endpoint doesn't connect to any other line (a loose end).",
}


def _precise_invalidity_point(geom):
    try:
        errors = geom.validateGeometry()
        if errors:
            pt = errors[0].where()
            return QgsGeometry.fromPointXY(pt)
    except Exception:
        pass
    return geom.centroid()


def _self_intersection_point(geom):
    return _precise_invalidity_point(geom)


class TopologyEngine(QObject):

    progress    = pyqtSignal(int, str)
    error_found = pyqtSignal(object)

    CHECKS_POLYGON = [
        TopologyError.INVALID_GEOMETRY, TopologyError.NULL_GEOMETRY,
        TopologyError.DUPLICATE_GEOMETRY, TopologyError.SELF_INTERSECTION,
        TopologyError.WRONG_TYPE_GEOMETRY,
    ]
    CHECKS_LINE = [
        TopologyError.INVALID_GEOMETRY, TopologyError.NULL_GEOMETRY,
        TopologyError.DUPLICATE_GEOMETRY, TopologyError.SELF_INTERSECTION,
        TopologyError.DANGLE, TopologyError.WRONG_TYPE_GEOMETRY,
    ]
    CHECKS_POINT = [
        TopologyError.INVALID_GEOMETRY, TopologyError.NULL_GEOMETRY,
        TopologyError.DUPLICATE_GEOMETRY,
    ]

    def __init__(self, parent=None):
        super(TopologyEngine, self).__init__(parent)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run_checks(self, layer, enabled_checks):
        self._cancelled = False
        errors = []
        if layer is None or not layer.isValid():
            return errors

        features  = list(layer.getFeatures())
        total     = len(features)
        if total == 0:
            return errors

        layer_name = layer.name()
        geom_type  = QgsWkbTypes.geometryType(layer.wkbType())

        use_spatial = any(c in enabled_checks for c in [
            TopologyError.DUPLICATE_GEOMETRY,
            TopologyError.DANGLE,
        ])
        spatial_index = QgsSpatialIndex() if use_spatial else None
        feat_map = {}

        # ── Pass 1: single-feature checks ────────────────────────────────
        for i, feat in enumerate(features):
            if self._cancelled:
                break

            self.progress.emit(int(i / total * 60),
                               "Checking feature {}/{}...".format(i + 1, total))
            fid  = feat.id()
            geom = feat.geometry()

            if TopologyError.NULL_GEOMETRY in enabled_checks:
                if geom is None or geom.isNull() or geom.isEmpty():
                    err = TopologyError(TopologyError.NULL_GEOMETRY, fid,
                                        layer_name, QgsGeometry(),
                                        "Feature has no geometry")
                    errors.append(err); self.error_found.emit(err)
                    if use_spatial:
                        feat_map[fid] = feat
                    continue

            if TopologyError.INVALID_GEOMETRY in enabled_checks:
                if not geom.isGeosValid():
                    precise_pt = _precise_invalidity_point(geom)
                    err = TopologyError(TopologyError.INVALID_GEOMETRY, fid,
                                        layer_name, precise_pt,
                                        "Geometry fails GEOS validity test")
                    errors.append(err); self.error_found.emit(err)

            if TopologyError.SELF_INTERSECTION in enabled_checks:
                if not geom.isSimple():
                    precise_pt = _self_intersection_point(geom)
                    err = TopologyError(TopologyError.SELF_INTERSECTION, fid,
                                        layer_name, precise_pt,
                                        "Geometry self-intersects")
                    errors.append(err); self.error_found.emit(err)

            if TopologyError.WRONG_TYPE_GEOMETRY in enabled_checks:
                if (not geom.isNull() and not geom.isEmpty()
                        and QgsWkbTypes.geometryType(geom.wkbType()) != geom_type):
                    err = TopologyError(TopologyError.WRONG_TYPE_GEOMETRY, fid,
                                        layer_name, geom.centroid(),
                                        "Feature geometry type ({}) does not match "
                                        "layer geometry type ({})".format(
                                            QgsWkbTypes.displayString(geom.wkbType()),
                                            QgsWkbTypes.displayString(layer.wkbType())))
                    errors.append(err); self.error_found.emit(err)

            if use_spatial:
                feat_map[fid] = feat
                spatial_index.addFeature(feat)

        # ── Pass 2: multi-feature checks ─────────────────────────────────
        if use_spatial and not self._cancelled:
            processed = set()
            for i, feat in enumerate(features):
                if self._cancelled:
                    break
                self.progress.emit(60 + int(i / total * 35),
                                   "Cross-checking feature {}/{}...".format(i + 1, total))
                fid  = feat.id()
                geom = feat.geometry()
                if geom is None or geom.isNull() or geom.isEmpty():
                    continue

                for cid in spatial_index.intersects(geom.boundingBox()):
                    if cid == fid:
                        continue
                    pair = (min(fid, cid), max(fid, cid))
                    if pair in processed:
                        continue
                    processed.add(pair)

                    other_geom = feat_map[cid].geometry() if cid in feat_map else None
                    if other_geom is None or other_geom.isNull():
                        continue

                    if TopologyError.DUPLICATE_GEOMETRY in enabled_checks:
                        if geom.equals(other_geom):
                            err = TopologyError(
                                TopologyError.DUPLICATE_GEOMETRY, fid, layer_name,
                                geom.centroid(),
                                "Duplicate of feature {}".format(cid))
                            errors.append(err); self.error_found.emit(err)

        # ── Dangle check: per-feature, all neighbors checked before flagging ──
        if (TopologyError.DANGLE in enabled_checks
                and geom_type == QgsWkbTypes.LineGeometry
                and spatial_index is not None
                and not self._cancelled):
            for feat in features:
                if self._cancelled:
                    break
                fid  = feat.id()
                geom = feat.geometry()
                if geom is None or geom.isNull() or geom.isEmpty():
                    continue
                vertices = list(geom.vertices())
                if not vertices:
                    continue
                for ep in [vertices[0], vertices[-1]]:
                    pt  = QgsGeometry.fromPointXY(QgsPointXY(ep.x(), ep.y()))
                    buf = pt.buffer(1e-8, 5)
                    neighbors = spatial_index.intersects(buf.boundingBox())
                    connected = any(
                        feat_map[cid].geometry().intersects(buf)
                        for cid in neighbors
                        if cid != fid and cid in feat_map
                    )
                    if not connected:
                        err = TopologyError(
                            TopologyError.DANGLE, fid, layer_name, pt,
                            "Dangling endpoint at ({:.4f}, {:.4f})".format(
                                ep.x(), ep.y()))
                        errors.append(err); self.error_found.emit(err)

        self.progress.emit(100, "Done - {} error(s) found.".format(len(errors)))
        return errors


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
        self._engine = TopologyEngine()

    def cancel(self):
        self._cancel = True
        self._engine.cancel()

    def run(self):
        grand = 0; n = len(self.layers)
        for li, layer in enumerate(self.layers):
            if self._cancel: break
            self.log.emit(f"Scanning: {layer.name()}  ({layer.featureCount()} features)")
            lg_name = QgsWkbTypes.displayString(layer.wkbType())
            geom_type = QgsWkbTypes.geometryType(layer.wkbType())

            # Map the checker-tab's simple checkbox flags onto the full
            # TopologyEngine check set, scoped to what applies to this layer's
            # geometry type (mirrors TopologyEngine.CHECKS_POLYGON/LINE/POINT).
            enabled = set()
            if self.checks.get("null"):    enabled.add(TopologyError.NULL_GEOMETRY)
            if self.checks.get("invalid"): enabled.add(TopologyError.INVALID_GEOMETRY)
            # "empty" has no direct TopologyEngine equivalent —
            # NULL_GEOMETRY already covers isNull()/isEmpty() together.
            if self.checks.get("empty"):   enabled.add(TopologyError.NULL_GEOMETRY)
            enabled |= {
                TopologyError.SELF_INTERSECTION, TopologyError.DUPLICATE_GEOMETRY,
                TopologyError.WRONG_TYPE_GEOMETRY, TopologyError.DANGLE,
            }
            if geom_type == QgsWkbTypes.PolygonGeometry:
                enabled &= set(TopologyEngine.CHECKS_POLYGON)
            elif geom_type == QgsWkbTypes.LineGeometry:
                enabled &= set(TopologyEngine.CHECKS_LINE)
            else:
                enabled &= set(TopologyEngine.CHECKS_POINT)

            counts = {}

            def _on_error(err, _layer=layer, _lg_name=lg_name):
                nonlocal grand
                counts[err.error_type] = counts.get(err.error_type, 0) + 1
                grand += 1
                try:
                    feat = next(_layer.getFeatures(
                        QgsFeatureRequest(err.fid)
                        .setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)), None)
                    full_geom = feat.geometry() if feat else None
                except Exception:
                    full_geom = None
                fg_name = "N/A"
                if full_geom is not None and not full_geom.isNull():
                    try: fg_name = QgsWkbTypes.displayString(full_geom.wkbType())
                    except: fg_name = "Unknown"
                self.issue_found.emit({
                    "layer": _layer, "layer_name": _layer.name(),
                    "feature_id": err.fid, "issue_type": err.error_type,
                    "layer_geom_type": _lg_name, "feature_geom_type": fg_name,
                    "geometry": full_geom,
                    # extras from the ported engine, used by the new
                    # PluginStyleFixerWorker and for zoom-to-error:
                    "topo_error_type": err.error_type,
                    "error_location": err.geometry,
                    "bbox": err.bbox,
                    "description": err.description,
                })

            self._engine.error_found.connect(_on_error)
            progress_slot = lambda pct, msg, _li=li: self.progress.emit(
                int(((_li + (pct / 100)) / n) * 100))
            self._engine.progress.connect(progress_slot)
            self._engine.run_checks(layer, enabled)
            self._engine.error_found.disconnect(_on_error)
            self._engine.progress.disconnect(progress_slot)

            for lbl, cnt in counts.items():
                if cnt: self.log.emit(f"   {lbl}: {cnt}")
            self.progress.emit(int(((li+1)/n)*100))
        self.log.emit(f"\nFinished. Total issues: {grand}")
        self.finished.emit(grand)


class PluginStyleFixerWorker(QThread):
    progress = pyqtSignal(int)
    log      = pyqtSignal(str)
    finished = pyqtSignal(int, int)   # fixed, skipped

    FIXABLE = (
        TopologyError.INVALID_GEOMETRY,
        TopologyError.SELF_INTERSECTION,
        TopologyError.NULL_GEOMETRY,
    )

    def __init__(self, layer, issues, delete_null=False):
        """issues: list of the issue_found dicts emitted by CheckWorker,
        already filtered to this layer. delete_null: must be pre-confirmed
        by the caller (UI) before running, since this worker has no dialog
        of its own — mirrors the plugin's QMessageBox.question guard."""
        super().__init__()
        self.layer = layer
        self.issues = issues
        self.delete_null = delete_null
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _apply_fix(self, fid, error_type):
        layer = self.layer
        if error_type == TopologyError.NULL_GEOMETRY:
            if not self.delete_null:
                return False, "Skipped (deletion not confirmed)."
            layer.startEditing()
            ok = layer.deleteFeature(fid)
            if ok:
                layer.commitChanges(); return True, f"Deleted FID {fid}."
            layer.rollBack(); return False, f"Could not delete FID {fid}."

        if error_type in (TopologyError.INVALID_GEOMETRY, TopologyError.SELF_INTERSECTION):
            feat = next(layer.getFeatures(f"$id = {fid}"), None)
            if not feat:
                return False, f"FID {fid} not found."
            fixed_geom = feat.geometry().makeValid()
            if not fixed_geom or fixed_geom.isNull():
                return False, f"makeValid() returned null for FID {fid}."
            layer.startEditing()
            ok = layer.changeGeometry(fid, fixed_geom)
            if ok:
                layer.commitChanges(); return True, f"Fixed {error_type} on FID {fid}."
            layer.rollBack(); return False, f"changeGeometry failed for FID {fid}."

        return False, f"No fix available for {error_type}."

    def run(self):
        fixed = 0; skipped = 0
        fixable = [i for i in self.issues if i.get("topo_error_type") in self.FIXABLE]
        total = len(fixable)
        for idx, issue in enumerate(fixable):
            if self._cancel:
                break
            ok, msg = self._apply_fix(issue["feature_id"], issue["topo_error_type"])
            self.log.emit(f"   {msg}")
            if ok: fixed += 1
            else:  skipped += 1
            self.progress.emit(int(((idx + 1) / max(total, 1)) * 100))
        self.layer.triggerRepaint()
        self.finished.emit(fixed, skipped)


# =============================================================================
# TAB 1 — GEOMETRY CHECKER UI
# =============================================================================

class CheckerTab(QWidget):

    # Which TopologyError / issue-type strings each internal repair mechanism
    # handles. "Repair Selected Features" is the single user-facing action;
    # under the hood it dispatches each checked row to the right mechanism
    # automatically based on its error type.
    REPAIR_TYPES = {"Invalid Geometry", "Wrong-type Geometry", TopologyError.SELF_INTERSECTION}  # -> PolygonFixerWorker (temp layer)
    NULL_TYPES   = {"Null Geometry", "Empty/Missing Geometry"}          # -> NullFixerWorker (temp layer)
    QUICK_TYPES  = set()                                                # -> PluginStyleFixerWorker (in-place) — none routed here anymore
    FIXABLE_TYPES = REPAIR_TYPES | NULL_TYPES | QUICK_TYPES

    def __init__(self):
        super().__init__()
        self.issues = []
        self.worker = None
        self.fix_queue = []
        self.fix_total_jobs = 0
        self.fix_done_jobs = 0
        self._error_marker = None   # QgsVertexMarker pinned on the exact error point
        self._error_rubber = None   # QgsRubberBand outlining the offending feature
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
        self.layer_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.layer_list.setAlternatingRowColors(True)
        self.layer_list.setToolTip("Click a layer to check/uncheck it as an input.")
        self.layer_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #b0bec5;
                outline: 0;
            }
            QListWidget::item {
                padding: 3px 4px;
            }
            QListWidget::indicator:checked {
                background-color: #1565c0;
                border: 1px solid #1565c0;
            }
        """)
        self._fill_layers()
        self.layer_list.setItemDelegate(LayerCheckDelegate(self.layer_list))
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
        self.table.setHorizontalHeaderLabels(["", "Layer", "Feature ID", "Error Type", "Layer Geom", "Feature Geom"])
        self._header_checkbox = CheckableHeaderView(Qt.Horizontal, self.table)
        self.table.setHorizontalHeader(self._header_checkbox)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(0, 28)
        self.table.setItemDelegateForColumn(0, CenteredCheckBoxDelegate(self.table))
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self._updating_error_checks = False
        self.table.horizontalHeader().sectionClicked.connect(self._handle_error_header_clicked)
        self.table.itemChanged.connect(self._handle_error_item_changed)
        rl.addWidget(self.table, stretch=1)

        legend = QLabel(
            '<span style="background-color:#ffffff; border:1px solid #999;">&nbsp;&nbsp;&nbsp;</span> '
            'Auto-fixable &nbsp;&nbsp;'
            '<span style="background-color:#ebebeb; border:1px solid #999;">&nbsp;&nbsp;&nbsp;</span> '
            'No automatic fix — manual review'
        )
        legend.setStyleSheet("font-size:11px; color:#455a64; padding:2px 0;")
        rl.addWidget(legend)

        # Repair panel is intentionally placed below the viewer so the workflow is:
        # Scan -> Review Issues -> Repair Selected Features (auto-detects fix mechanism per row).
        self.repair_group = QGroupBox(""); self.repair_group.setStyleSheet(GRP_STYLE)
        gf = QVBoxLayout(self.repair_group)
        gf.setContentsMargins(10, 24, 10, 10)
        gf.setSpacing(7)

        repair_note = QLabel(
            "Note: the scan above is an initial reference to locate errors, not a "
            "final diagnosis — some issues may need closer review. Repair Selected "
            "Features will not resolve every error automatically, and its output "
            "still needs to be reviewed: for example, a single feature can explode "
            "into multiple parts during repair, changing the feature count. Always "
            "check the repaired output before treating it as final."
        )
        repair_note.setWordWrap(True)
        repair_note.setStyleSheet("font-size:11px; color:#8a6d3b; padding:2px 0 4px 0;")
        gf.addWidget(repair_note)

        self.fix_btn = QPushButton("Repair Selected Features")
        self.fix_btn.setFixedHeight(32); self.fix_btn.setStyleSheet(BTN_EXPORT)
        self.fix_btn.setEnabled(False)
        self.fix_btn.setToolTip(
            "Repairs every checked row using the appropriate fixer automatically:\n"
            "- Invalid Geometry / Wrong-type Geometry / Self Intersection -> thorough repair (new temporary layer)\n"
            "- Null / Empty Geometry -> recovery from surrounding polygons (new temporary layer)")
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
        self.btn_all.clicked.connect(self._check_all_layers)
        self.btn_none.clicked.connect(self._uncheck_all_layers)
        self.layer_list.itemChanged.connect(self._update_layer_count_label)

        # Keep the input layer viewer updated when polygon layers are added or removed in QGIS.
        QgsProject.instance().layersAdded.connect(self._refresh_layers_keep_selection)
        QgsProject.instance().layersRemoved.connect(self._refresh_layers_keep_selection)

        self.fix_btn.clicked.connect(self._fix_checked_errors)
        self.table.cellDoubleClicked.connect(self._zoom)

    def _check_all_layers(self):
        self.layer_list.blockSignals(True)
        for i in range(self.layer_list.count()):
            self.layer_list.item(i).setCheckState(Qt.Checked)
        self.layer_list.blockSignals(False)
        self._update_layer_count_label()

    def _uncheck_all_layers(self):
        self.layer_list.blockSignals(True)
        for i in range(self.layer_list.count()):
            self.layer_list.item(i).setCheckState(Qt.Unchecked)
        self.layer_list.blockSignals(False)
        self._update_layer_count_label()

    def _fill_layers(self, keep_selected_ids=None):
        """Refresh the input layer list from the current QGIS project.

        keep_selected_ids preserves the user's checked layers when QGIS
        layers are added or removed. This makes the layer viewer feel live while
        avoiding accidental loss of selected inputs.
        """
        keep_selected_ids = set(keep_selected_ids or [])
        self.layer_list.blockSignals(True)
        self.layer_list.clear(); self._lmap = {}
        for lid, lyr in get_polygon_layers().items():
            item = QListWidgetItem(lyr.name()); item.setData(Qt.UserRole, lid)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if lid in keep_selected_ids else Qt.Unchecked)
            self.layer_list.addItem(item); self._lmap[lid] = lyr
        self.layer_list.blockSignals(False)

    def _selected_layer_ids(self):
        return [self.layer_list.item(i).data(Qt.UserRole) for i in range(self.layer_list.count())
                if self.layer_list.item(i).checkState() == Qt.Checked]

    def _selected(self):
        return [self._lmap[lid] for lid in self._selected_layer_ids() if lid in self._lmap]

    def _update_layer_count_label(self):
        if not hasattr(self, "layer_count_label"):
            return
        selected = len(self._selected_layer_ids())
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
        checks = {"null": True, "empty": True, "invalid": True}
        self.issues = []; self.table.setRowCount(0); self._update_error_header_checkbox(); self.log_box.clear()
        self.progress.setValue(0); self.summary.setText("Scanning geometry errors...")
        self.fix_btn.setEnabled(False); self.repair_group.setEnabled(False)
        self.run_btn.setEnabled(False); self.cancel_btn.setEnabled(True)
        self._clear_error_highlight()
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
        self.summary.setText(f"Scan complete - {total} error(s) found. Check errors in the viewer panel, then click Repair Selected Features.")
        self._apply_fix_type_filter()

    def _add_row(self, data):
        self.issues.append(data)
        row = self.table.rowCount(); self.table.insertRow(row)
        issue = data["issue_type"]
        self._updating_error_checks = True
        chk = QTableWidgetItem("")
        chk.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
        chk.setCheckState(Qt.Unchecked)
        chk.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 0, chk)
        self.table.setItem(row, 1, QTableWidgetItem(data["layer_name"]))
        self.table.setItem(row, 2, QTableWidgetItem(str(data["feature_id"])))
        self.table.setItem(row, 3, colored_item(issue, issue))
        self.table.setItem(row, 4, QTableWidgetItem(data["layer_geom_type"]))
        self.table.setItem(row, 5, QTableWidgetItem(data["feature_geom_type"]))
        self._updating_error_checks = False
        self._apply_fix_type_filter()

    def _row_status(self, row):
        """Returns 'fixable' if Repair Selected Features can act on this row
        (regardless of which internal mechanism it uses), otherwise 'none'."""
        if row >= len(self.issues):
            return "none"
        issue = self.issues[row]["issue_type"]
        return "fixable" if issue in self.FIXABLE_TYPES else "none"

    def _is_row_compatible_with_current_fix_type(self, row):
        return self._row_status(row) == "fixable"

    def _apply_fix_type_filter(self):
        """Style every error row by whether Repair Selected Features can handle it:
        - white / black : fixable (checkbox enabled)
        - grey          : no automatic fix available — manual review only (checkbox disabled)
        """
        grey_bg  = QColor(235, 235, 235); grey_fg  = QColor(140, 140, 140)
        white_bg = QColor(255, 255, 255); black_fg = QColor(0, 0, 0)

        fixable_count = 0
        none_count = 0

        for row in range(self.table.rowCount()):
            status = self._row_status(row)
            issue = self.issues[row]["issue_type"] if row < len(self.issues) else ""
            chk = self.table.item(row, 0)

            desc = ERROR_TYPE_DESCRIPTIONS.get(issue, "")

            if status == "fixable":
                fixable_count += 1
                tip = f"{desc}\n\nHandled automatically by Repair Selected Features." if desc else \
                      "Handled automatically by Repair Selected Features."
                bg, fg, enable_chk = white_bg, black_fg, True
            else:
                none_count += 1
                tip = (f"{desc}\n\nNo automatic fix available — manual review required." if desc else
                       f"No automatic fix available for {issue} — manual review required.")
                bg, fg, enable_chk = grey_bg, grey_fg, False

            if chk:
                if enable_chk:
                    chk.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
                else:
                    chk.setCheckState(Qt.Unchecked)
                    chk.setFlags(Qt.ItemIsSelectable)
                chk.setToolTip(tip)

            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if not item:
                    continue
                item.setBackground(bg); item.setForeground(fg); item.setToolTip(tip)

        self._update_error_header_checkbox()
        self.fix_btn.setEnabled(bool(self.issues) and fixable_count > 0)
        if self.issues:
            self.summary.setText(
                f"{fixable_count} fixable by Repair Selected Features, "
                f"{none_count} manual review only."
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
            self._header_checkbox.setCheckState(Qt.Unchecked)
            return
        checked_rows = [
            row for row in compatible_rows
            if self.table.item(row, 0) and self.table.item(row, 0).checkState() == Qt.Checked
        ]
        if len(checked_rows) == len(compatible_rows):
            state = Qt.Checked
        elif checked_rows:
            state = Qt.PartiallyChecked
        else:
            state = Qt.Unchecked
        self._header_checkbox.setCheckState(state)
        self._header_checkbox.setToolTip("Click to select or clear all auto-fixable errors.")

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

    def _fix_checked_errors(self):
        rows = self._checked_issue_rows()
        if not rows:
            return QMessageBox.warning(self, "No Errors Selected", "Check at least one auto-fixable error in the viewer panel, or highlight rows in the table.")

        jobs = {}
        skipped = []
        for row in rows:
            d = self.issues[row]
            issue = d["issue_type"]
            layer = d["layer"]
            if issue in self.REPAIR_TYPES:
                key = (layer.id(), "polygon")
                jobs.setdefault(key, {"layer": layer, "kind": "polygon", "ids": set()})["ids"].add(d["feature_id"])
            elif issue in self.NULL_TYPES:
                key = (layer.id(), "null")
                jobs.setdefault(key, {"layer": layer, "kind": "null", "ids": set()})["ids"].add(d["feature_id"])
            elif issue in self.QUICK_TYPES:
                key = (layer.id(), "quick")
                jobs.setdefault(key, {"layer": layer, "kind": "quick", "issues": []})["issues"].append(d)
            else:
                skipped.append(f"FID {d['feature_id']} ({issue})")

        if not jobs:
            return QMessageBox.warning(
                self, "No Fixable Errors",
                "The checked rows are not handled by Repair Selected Features."
            )

        if skipped:
            self._log("Skipped rows with no automatic fix:")
            for msg in skipped[:20]: self._log("  - " + msg)
            if len(skipped) > 20: self._log(f"  ...and {len(skipped)-20} more")

        self.fix_queue = list(jobs.values())
        self.fix_total_jobs = len(self.fix_queue)
        self.fix_done_jobs = 0
        self.fix_layer_outputs = {}   # source layer id -> canonical "_FIXED" output layer for this run
        self.fix_touched_attrs = {}   # source layer id -> set of attribute tuples this run actually modified
        self.run_btn.setEnabled(False); self.fix_btn.setEnabled(False); self.repair_group.setEnabled(False); self.cancel_btn.setEnabled(True)
        self.progress.setValue(0)
        self.summary.setText("Repairing selected features…")
        self._start_next_fix_job()

    def _explode_and_clean_outputs(self):
        """Run once after all repair jobs in this run finish.

        The polygon reconstruction pipeline (Polygons-to-Lines -> Polygonize
        -> pick candidate faces -> unaryUnion) can occasionally produce a
        multipart result for what was originally a single-part feature, e.g.
        when the rebuild picks up two disjoint candidate faces for one fid.
        For any feature this run actually modified, this explodes the
        result with "Multipart to singleparts" and removes fragments that
        are clearly reconstruction artifacts rather than real features: a
        part that is empty, or negligibly small compared to another part
        sharing the exact same original attributes (the "same fid, one part
        zooms in fine, the other doesn't" case).

        Only rows this run's fixer jobs actually changed (tracked via
        touched_attrs on each worker) are ever considered here. Pre-existing
        multipart features that were simply copied through unchanged — e.g.
        a barangay that legitimately includes an offshore island — are left
        completely alone, even if this whole output layer contains other
        multipart geometry elsewhere.
        """
        AREA_ISH_RATIO = 1e-4  # a fragment under this fraction of its largest same-attribute sibling is treated as a sliver artifact, not a real feature

        for key, out_lyr in list(self.fix_layer_outputs.items()):
            if out_lyr is None:
                continue

            touched = self.fix_touched_attrs.get(key, set())
            if not touched:
                continue

            try:
                touched_multipart = any(
                    f.hasGeometry() and f.geometry().isMultipart()
                    and tuple(f.attributes()) in touched
                    for f in out_lyr.getFeatures()
                )
            except Exception:
                touched_multipart = False
            if not touched_multipart:
                continue

            self._log(f"\n{out_lyr.name()}: multipart geometry found in a repaired feature — "
                       f"running Multipart to Singleparts on the affected row(s)...")

            # Split into "rows this run touched" (candidates for exploding /
            # sliver cleanup / merge-back) and "everything else" (left
            # completely untouched, copied straight through as-is).
            touched_lyr = QgsVectorLayer(
                f"{QgsWkbTypes.displayString(out_lyr.wkbType())}?crs={out_lyr.crs().authid()}",
                "_touched_subset", "memory")
            touched_lyr.setCrs(out_lyr.crs())  # authid() can be empty for custom/undefined CRS — set explicitly so the layer never silently ends up with no CRS
            touched_lyr.dataProvider().addAttributes(out_lyr.fields()); touched_lyr.updateFields()
            touched_lyr.startEditing()
            rest_feats = []
            for f in out_lyr.getFeatures():
                if tuple(f.attributes()) in touched:
                    nf = QgsFeature(touched_lyr.fields())
                    nf.setGeometry(f.geometry()); nf.setAttributes(f.attributes())
                    touched_lyr.addFeature(nf)
                else:
                    rest_feats.append(f)
            touched_lyr.commitChanges(); touched_lyr.updateExtents()

            try:
                res = processing.run("native:multiparttosingleparts",
                                      {"INPUT": touched_lyr, "OUTPUT": "TEMPORARY_OUTPUT"})
                split_lyr = res["OUTPUT"]
            except Exception as e:
                self._log(f"  Could not explode multipart output: {e}")
                continue

            # native:multiparttosingleparts always declares its output layer
            # as single-part — even though the merge-back step below can
            # write MultiPolygon geometry into it for genuine multi-part
            # survivors. changeGeometry() lets that happen silently, but the
            # layer's declared type stays single-part, which is exactly what
            # QGIS's native "Merge Selected Features" checks and rejects
            # later ("geometry type (multipart) is incompatible with layer
            # type (singlepart)"). Promote to the Multi-type variant now,
            # before any further edits, so the layer stays fully compatible.
            multi_wkb = QgsWkbTypes.multiType(split_lyr.wkbType())
            if multi_wkb != split_lyr.wkbType():
                promoted = QgsVectorLayer(
                    f"{QgsWkbTypes.displayString(multi_wkb)}?crs={split_lyr.crs().authid()}",
                    split_lyr.name(), "memory")
                promoted.setCrs(split_lyr.crs())
                promoted.dataProvider().addAttributes(split_lyr.fields()); promoted.updateFields()
                promoted.startEditing()
                for f in split_lyr.getFeatures():
                    nf = QgsFeature(promoted.fields())
                    nf.setGeometry(f.geometry()); nf.setAttributes(f.attributes())
                    promoted.addFeature(nf)
                promoted.commitChanges(); promoted.updateExtents()
                split_lyr = promoted

            # Group parts by their original attributes to find same-fid siblings,
            # and size each part (area for polygons, length for lines).
            sizes_by_attrs = {}
            for f in split_lyr.getFeatures():
                geom = f.geometry()
                if geom is None or geom.isEmpty():
                    size = 0.0
                else:
                    gt = QgsWkbTypes.geometryType(geom.wkbType())
                    if gt == QgsWkbTypes.PolygonGeometry:
                        size = geom.area()
                    elif gt == QgsWkbTypes.LineGeometry:
                        size = geom.length()
                    else:
                        size = 1.0
                sizes_by_attrs.setdefault(tuple(f.attributes()), []).append((f.id(), size))

            removed = []
            for attrs, parts in sizes_by_attrs.items():
                if len(parts) < 2:
                    continue
                max_size = max(sz for _, sz in parts)
                if max_size <= 0:
                    continue
                for fid, sz in parts:
                    if sz <= 0 or (sz / max_size) < AREA_ISH_RATIO:
                        removed.append(fid)

            if removed:
                split_lyr.startEditing()
                for fid in removed:
                    split_lyr.deleteFeature(fid)
                split_lyr.commitChanges(); split_lyr.updateExtents()
                self._log(f"  Removed {len(removed)} sliver/artifact fragment(s) "
                          f"produced by the explode step (empty or negligible in "
                          f"size next to a same-feature sibling).")
            else:
                self._log("  No sliver fragments found after exploding.")

            # Re-merge any genuine multi-part survivors (2+ real parts sharing
            # the same original attributes) back into one multipart feature,
            # instead of leaving them as separate duplicate-attribute rows.
            removed_set = set(removed)
            survivor_groups = {}
            for attrs, parts in sizes_by_attrs.items():
                survivors = [fid for fid, sz in parts if fid not in removed_set]
                if len(survivors) > 1:
                    survivor_groups[attrs] = survivors

            merged_count = 0
            if survivor_groups:
                split_lyr.startEditing()
                for attrs, fids in survivor_groups.items():
                    geoms = []
                    for fid in fids:
                        feat = split_lyr.getFeature(fid)
                        if feat and feat.hasGeometry():
                            geoms.append(feat.geometry())
                    if len(geoms) < 2:
                        continue
                    merged_geom = QgsGeometry.unaryUnion(geoms)
                    keep_fid, drop_fids = fids[0], fids[1:]
                    split_lyr.changeGeometry(keep_fid, merged_geom)
                    for fid in drop_fids:
                        split_lyr.deleteFeature(fid)
                    merged_count += 1
                split_lyr.commitChanges(); split_lyr.updateExtents()
                self._log(f"  Merged {merged_count} feature(s) that resolved into "
                          f"multiple real parts back into a single multipart "
                          f"feature (kept as one row instead of duplicating attributes).")

            # Rebuild the final output layer: the untouched rows exactly as
            # they were, plus the cleaned/merged touched rows. Everything
            # this run never selected for repair — including pre-existing
            # legitimate multipart features like islands — passes through
            # completely unchanged.
            final_wkb = QgsWkbTypes.multiType(out_lyr.wkbType())
            final_lyr = QgsVectorLayer(
                f"{QgsWkbTypes.displayString(final_wkb)}?crs={out_lyr.crs().authid()}",
                out_lyr.name(), "memory")
            final_lyr.setCrs(out_lyr.crs())
            final_lyr.dataProvider().addAttributes(out_lyr.fields()); final_lyr.updateFields()
            final_lyr.startEditing()
            for f in rest_feats:
                nf = QgsFeature(final_lyr.fields())
                nf.setGeometry(f.geometry()); nf.setAttributes(f.attributes())
                final_lyr.addFeature(nf)
            for f in split_lyr.getFeatures():
                nf = QgsFeature(final_lyr.fields())
                nf.setGeometry(f.geometry()); nf.setAttributes(f.attributes())
                final_lyr.addFeature(nf)
            final_lyr.commitChanges(); final_lyr.updateExtents()

            QgsProject.instance().removeMapLayer(out_lyr.id())
            QgsProject.instance().addMapLayer(final_lyr)
            self.fix_layer_outputs[key] = final_lyr

    def _start_next_fix_job(self):
        if not self.fix_queue:
            self._explode_and_clean_outputs()
            self.run_btn.setEnabled(True); self.fix_btn.setEnabled(bool(self.issues)); self.repair_group.setEnabled(bool(self.issues)); self.cancel_btn.setEnabled(False)
            self.progress.setValue(100)
            self.summary.setText(f"Repair complete - {self.fix_done_jobs}/{self.fix_total_jobs} job(s) processed.")
            self._apply_fix_type_filter()
            return

        job = self.fix_queue.pop(0)
        layer = job["layer"]; kind = job["kind"]
        self.fix_done_jobs_display = self.fix_done_jobs + 1
        self.current_job_layer = layer
        self.current_job_ids = set(job.get("ids", []))

        if kind == "polygon":
            ids = sorted(job["ids"])
            self._log(f"\n=== Repair job {self.fix_done_jobs + 1}/{self.fix_total_jobs}: {layer.name()} | Invalid / Wrong-type / Self-Intersection Geometry | features: {len(ids)} ===")
            self.worker = PolygonFixerWorker(layer, True, selected_ids=ids)
            self.worker.finished.connect(self._done_fixer)
        elif kind == "null":
            ids = sorted(job["ids"])
            self._log(f"\n=== Repair job {self.fix_done_jobs + 1}/{self.fix_total_jobs}: {layer.name()} | Null / Empty Geometry | features: {len(ids)} ===")
            self.worker = NullFixerWorker(layer, True, selected_ids=ids)
            self.worker.finished.connect(self._done_null)
        else:  # "quick"
            issues = job["issues"]
            self._log(f"\n=== Repair job {self.fix_done_jobs + 1}/{self.fix_total_jobs}: {layer.name()} | (in-place fixer — not currently used by any error type) | features: {len(issues)} ===")
            self.worker = PluginStyleFixerWorker(layer, issues, delete_null=False)
            self.worker.finished.connect(self._done_quick)

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

    def _merge_fix_output(self, source_layer, new_lyr, target_fids):
        """Merge a fixer job's output into the single canonical "_FIXED" layer
        for this source layer, so multiple fixer jobs on the same layer (e.g.
        Wrong-type Geometry + Null Geometry) don't each create their own
        separate "_FIXED"/"_RECOVERED" output layer.

        The first job for a given source layer becomes the canonical output.
        Every later job for that same source layer copies over only the
        geometries it fixed (target_fids) into the canonical layer, then its
        own (now-redundant) output layer is removed from the project.
        """
        if new_lyr is None:
            return
        key = source_layer.id()
        canonical = self.fix_layer_outputs.get(key)

        if canonical is None:
            self.fix_layer_outputs[key] = new_lyr
            return

        req = QgsFeatureRequest().setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)
        src_fids_in_order = [f.id() for f in source_layer.getFeatures(req)]
        c_feats = list(canonical.getFeatures())
        n_feats = list(new_lyr.getFeatures())

        if len(c_feats) == len(n_feats) == len(src_fids_in_order):
            canonical.startEditing()
            merged = 0
            for pos, src_fid in enumerate(src_fids_in_order):
                if src_fid in target_fids:
                    canonical.changeGeometry(c_feats[pos].id(), n_feats[pos].geometry())
                    merged += 1
            canonical.commitChanges(); canonical.updateExtents()
            QgsProject.instance().removeMapLayer(new_lyr.id())
            self._log(f"Merged {merged} repaired feature(s) into {canonical.name()}.")
        else:
            # Feature counts don't line up (e.g. a job was cancelled partway) —
            # keep both outputs rather than risk merging the wrong geometries.
            self._log("Could not merge repair outputs (feature count mismatch) — "
                       f"kept {new_lyr.name()} as a separate layer.")

    def _done_fixer(self, fixed, copied):
        self.fix_done_jobs += 1
        self._log(f"Output created. Fixed: {fixed}   Copied: {copied}")
        self._merge_fix_output(self.current_job_layer, self.worker.output_layer, self.current_job_ids)
        key = self.current_job_layer.id()
        self.fix_touched_attrs.setdefault(key, set()).update(getattr(self.worker, "touched_attrs", set()))
        self._start_next_fix_job()

    def _done_null(self, recovered, copied, manual):
        self.fix_done_jobs += 1
        self._log(f"Output created. Recovered: {recovered}   Manual review: {manual}   Copied: {copied}")
        self._merge_fix_output(self.current_job_layer, self.worker.output_layer, self.current_job_ids)
        key = self.current_job_layer.id()
        self.fix_touched_attrs.setdefault(key, set()).update(getattr(self.worker, "touched_attrs", set()))
        self._start_next_fix_job()

    def _done_quick(self, fixed, skipped):
        self.fix_done_jobs += 1
        self._log(f"In-place fix complete. Fixed: {fixed}   Skipped: {skipped}")
        self._start_next_fix_job()

    def _clear_error_highlight(self):
        """Remove any previously drawn error marker/outline from the canvas."""
        canvas = iface.mapCanvas()
        if self._error_marker is not None:
            try:
                canvas.scene().removeItem(self._error_marker)
            except Exception:
                pass
            self._error_marker = None
        if self._error_rubber is not None:
            try:
                canvas.scene().removeItem(self._error_rubber)
            except Exception:
                pass
            self._error_rubber = None

    def _zoom(self, row, _):
        if row >= len(self.issues): return
        d = self.issues[row]
        try:
            layer = d.get("layer")
            canvas = iface.mapCanvas()
            self._clear_error_highlight()

            # Fetch the full feature so we have a real reference size for
            # this feature, in its own native units. This is what fixes the
            # "zoom out to the whole world" bug: the old code used a fixed
            # 500-5000 map-unit window (via TopologyError.bbox), which is a
            # sane window in metres but is enormous for a degrees-based
            # (EPSG:4326-style) layer. Scaling to the feature's own extent
            # works the same regardless of whether the layer uses metres,
            # feet, or degrees.
            feat = None
            try:
                feat = next(layer.getFeatures(
                    QgsFeatureRequest(d["feature_id"])
                    .setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)), None)
            except Exception:
                feat = None
            full_geom = feat.geometry() if feat else d.get("geometry")

            err_geom = d.get("error_location")
            has_precise_point = (
                err_geom is not None and not err_geom.isNull()
                and not err_geom.isEmpty()
                and err_geom.type() == QgsWkbTypes.PointGeometry
            )

            bb = None
            if has_precise_point and full_geom is not None and not full_geom.isNull() and not full_geom.isEmpty():
                feat_bb = full_geom.boundingBox()
                span = max(feat_bb.width(), feat_bb.height())
                half = span * 0.12 if span > 0 else 0
                if half <= 0:
                    # Degenerate/point feature — use a small fraction of the
                    # layer's own extent instead of guessing absolute units.
                    layer_extent = layer.extent()
                    half = max(layer_extent.width(), layer_extent.height()) * 0.01
                pt = err_geom.asPoint()
                bb = QgsRectangle(pt.x() - half, pt.y() - half, pt.x() + half, pt.y() + half)
            elif full_geom is not None and not full_geom.isNull() and not full_geom.isEmpty():
                bb = full_geom.boundingBox(); bb.scale(1.5)

            if bb is None:
                self._log(f"Cannot zoom: FID {d['feature_id']} has Null/Empty geometry.")
                return

            # bb (and any geometry drawn on the canvas) is in the source
            # layer's CRS — reproject to the canvas CRS before applying, so
            # this also behaves correctly on projects using on-the-fly
            # reprojection.
            layer_crs = layer.crs()
            canvas_crs = canvas.mapSettings().destinationCrs()
            xform = None
            if layer_crs.isValid() and canvas_crs.isValid() and layer_crs != canvas_crs:
                try:
                    xform = QgsCoordinateTransform(layer_crs, canvas_crs, QgsProject.instance())
                    bb = xform.transformBoundingBox(bb)
                except Exception as e:
                    self._log(f"CRS transform failed, zoom may be off: {e}")
                    xform = None

            canvas.setExtent(bb); canvas.refresh()

            # ── Visual sign: outline the offending feature in red, and pin
            # an X marker on the exact error vertex/point, so it's obvious
            # at a glance which feature and which spot triggered the error.
            if full_geom is not None and not full_geom.isNull() and not full_geom.isEmpty():
                rb_geom = QgsGeometry(full_geom)
                if xform is not None:
                    try:
                        rb_geom.transform(xform)
                    except Exception:
                        rb_geom = None
                if rb_geom is not None:
                    rb_type = (QgsWkbTypes.PolygonGeometry
                               if full_geom.type() == QgsWkbTypes.PolygonGeometry
                               else QgsWkbTypes.LineGeometry)
                    rb = QgsRubberBand(canvas, rb_type)
                    rb.setColor(QColor(255, 0, 0, 220))
                    rb.setFillColor(QColor(255, 0, 0, 0))  # outline only
                    rb.setWidth(3)
                    rb.setToGeometry(rb_geom, None)
                    self._error_rubber = rb

            if has_precise_point:
                pt_geom = QgsGeometry(err_geom)
                if xform is not None:
                    try:
                        pt_geom.transform(xform)
                    except Exception:
                        pt_geom = None
                if pt_geom is not None and not pt_geom.isNull():
                    marker = QgsVertexMarker(canvas)
                    marker.setCenter(pt_geom.asPoint())
                    marker.setColor(QColor(255, 0, 0))
                    marker.setIconType(QgsVertexMarker.ICON_X)
                    marker.setIconSize(14)
                    marker.setPenWidth(3)
                    self._error_marker = marker

            self._log(f"Zoomed to error: FID {d['feature_id']} ({d.get('issue_type', '')}) in {d['layer_name']}")
        except Exception as e:
            self._log(f"Zoom failed: {e}")

    def _clear(self):
        self.issues = []; self.table.setRowCount(0); self._update_error_header_checkbox(); self.log_box.clear()
        self.progress.setValue(0); self.summary.setText("Results cleared.")
        self.fix_btn.setEnabled(False); self.repair_group.setEnabled(False)
        self._clear_error_highlight()


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
        self.output_layer = None   # set to the created "_FIXED" memory layer once run() builds it
        self.touched_attrs = set()  # attribute tuples of rows this worker actually changed (not copied through)

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

    def _raw_makevalid_last_resort(self, geom, output_wkb):
        """Bypass _clean()'s strict Polygon/GeometryCollection filtering and
        accept a raw makeValid() result directly — same approach Topology
        Checker Pro's Auto-Fix uses. Only called after our own multi-step
        cleanup chain (_clean -> polygonize/union -> QGIS Fix Geometries)
        has already failed, so this never overrides a better result."""
        if geom is None or geom.isEmpty():
            return None
        try:
            raw_fix = geom.makeValid()
        except Exception:
            return None
        if not raw_fix or raw_fix.isEmpty():
            return None
        raw_fit = self._fit_output_wkb(raw_fix, output_wkb)
        if raw_fit and self._is_valid_polygon_geom(raw_fit):
            return raw_fit
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
            tmp.setCrs(source_layer.crs())
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
                tmp.setCrs(source_layer.crs())
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
        tmp.setCrs(source_layer.crs())
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

        # Always build the output as the Multi-type variant of the layer's
        # geometry type (preserving Z/M), regardless of whether the source
        # layer is declared single-part. The reconstruction (unaryUnion of
        # candidate faces) can legitimately produce a MultiPolygon result
        # even for a single feature — writing that into a strictly
        # single-part memory layer fails the ENTIRE commit ("N feature(s)
        # not added — geometry type is not compatible"), not just that one
        # feature. Multi-typed layers safely accept single-part geometries
        # too, so this is always compatible either way.
        out_wkb = QgsWkbTypes.multiType(layer.wkbType())
        out_uri = QgsWkbTypes.displayString(out_wkb) + f"?crs={layer.crs().authid()}"
        out_lyr = QgsVectorLayer(out_uri, layer.name() + "_FIXED", "memory")
        out_lyr.setCrs(layer.crs())  # authid() can be empty for custom/undefined CRS — set explicitly so the output never silently ends up with no CRS
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
                    out.setGeometry(qfix); self.touched_attrs.add(tuple(out.attributes())); out_lyr.addFeature(out); fixed += 1
                    self.log.emit(f"   FID {feat.id()} repaired using QGIS Fix Geometries fallback.")
                    continue

                raw_fit = self._raw_makevalid_last_resort(orig, layer.wkbType())
                if raw_fit:
                    out.setGeometry(raw_fit); self.touched_attrs.add(tuple(out.attributes())); out_lyr.addFeature(out); fixed += 1
                    self.log.emit(f"   FID {feat.id()} repaired using raw makeValid() last-resort fallback.")
                    continue

                out.setGeometry(orig); self.touched_attrs.add(tuple(out.attributes())); out_lyr.addFeature(out); copied += 1
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
                        if inter and not inter.isEmpty() and inter.area() > 0:
                            # Use the clipped intersection, not the whole polygonize
                            # face — polygonize runs over ALL selected features'
                            # boundaries at once, so a face can extend beyond this
                            # feature's own footprint into a neighbor's area. Taking
                            # the raw face here would union that extra area in and
                            # create a new overlap with the neighbor.
                            cands.append(inter)
                except:
                    if pg.boundingBox().intersects(co.boundingBox()):
                        try:
                            clipped = pg.intersection(co)
                            cands.append(clipped if clipped and not clipped.isEmpty() else pg)
                        except:
                            cands.append(pg)

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
                            raw_fit = self._raw_makevalid_last_resort(orig, layer.wkbType())
                            if raw_fit:
                                out.setGeometry(raw_fit); fixed += 1
                                self.log.emit(f"   FID {feat.id()} repaired using raw makeValid() last-resort fallback.")
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
                        raw_fit = self._raw_makevalid_last_resort(orig, layer.wkbType())
                        if raw_fit:
                            out.setGeometry(raw_fit); fixed += 1
                            self.log.emit(f"   FID {feat.id()} repaired using raw makeValid() last-resort fallback.")
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

            self.touched_attrs.add(tuple(out.attributes()))
            out_lyr.addFeature(out)

        out_lyr.commitChanges(); out_lyr.updateExtents()
        self.output_layer = out_lyr
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
        self.output_layer = None   # set to the created "_FIXED" memory layer once run() builds it
        self.touched_attrs = set()  # attribute tuples of rows this worker actually changed (not copied through)

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
        valid_lyr.setCrs(layer.crs())
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
        # polygonized faces are returned by QGIS as 2D geometries. Also force
        # the Multi-type variant — a recovered/largest-polygonized-face
        # geometry can come back as MultiPolygon even for a single-part
        # layer, and a strictly single-part memory layer would reject the
        # ENTIRE batch on commit rather than just that one feature.
        out_wkb = QgsWkbTypes.multiType(QgsWkbTypes.flatType(layer.wkbType()))
        out_lyr = QgsVectorLayer(
            f"{QgsWkbTypes.displayString(out_wkb)}?crs={layer.crs().authid()}",
            layer.name() + "_FIXED", "memory")
        out_lyr.setCrs(layer.crs())  # authid() can be empty for custom/undefined CRS — set explicitly so the output never silently ends up with no CRS
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
                self.touched_attrs.add(tuple(attrs))
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
        self.output_layer = out_lyr
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
        self.radio_polygon  = QRadioButton("Polygon Fix  (Invalid Geometry)")
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
        <h2>Geometry Repair Toolkit</h2>
        <p>
        This tool checks polygon layers for geometry errors and creates temporary repaired output layers.
        The original input layer is never edited by any of the repair fixers — Invalid, Wrong-type,
        Self Intersection, and Null/Empty are all repaired into a new temporary output layer.
        </p>

        <h3>How to Use</h3>
        <ol>
            <li>Select one or more polygon layers from <b>Input Layers</b>.</li>
            <li>Click <b>Scan Layers</b>.</li>
            <li>Review the detected errors in the table. White rows are auto-fixable; grey rows need manual review.</li>
            <li>Check the errors to repair. You may also click the checkbox in the first column header to select or clear all auto-fixable errors.</li>
            <li>Click <b>Repair Selected Features</b>. It automatically applies the right fixer to each checked row (Invalid, Wrong-type, Self-Intersection, or Null/Empty).</li>
            <li>Review the resulting temporary output layer(s) before saving or replacing any source data.</li>
        </ol>

        <h3>Error Types</h3>
        <table border="1" cellspacing="0" cellpadding="5">
            <tr><th>Error Type</th><th>Description</th></tr>
            <tr>
                <td><b>Null Geometry</b></td>
                <td>The feature record exists, but there is no geometry object.</td>
            </tr>
            <tr>
                <td><b>Empty/Missing Geometry</b></td>
                <td>The feature exists, but its geometry has no usable shape or coordinates.</td>
            </tr>
            <tr>
                <td><b>Invalid Geometry</b></td>
                <td>The polygon has geometry errors such as self-intersection, ring error, spike, or folded edge.</td>
            </tr>
            <tr>
                <td><b>Self Intersection</b></td>
                <td>The polygon crosses itself.</td>
            </tr>
            <tr>
                <td><b>Wrong-type Geometry</b></td>
                <td>The feature's geometry type does not match the layer's declared geometry type (e.g. a line or GeometryCollection stored in a polygon layer).</td>
            </tr>
        </table>

        <h3>Repair Selected Features</h3>
        <p>
        This is the single action used to fix any checked, auto-fixable row. It inspects each checked
        row's error type and automatically routes it to the correct mechanism:
        </p>
        <ul>
            <li><b>Invalid Geometry / Wrong-type Geometry / Self Intersection</b> — thorough polygon reconstruction, written to a new temporary output layer.</li>
            <li><b>Null / Empty / Missing Geometry</b> — recovery from surrounding polygons, written to a new temporary output layer.</li>
        </ul>
        <p>
        The polygon reconstruction can occasionally leave a feature multipart even though it started as a
        single part. When that happens on a feature this run actually repaired, the toolkit automatically
        runs <b>Multipart to Singleparts</b> on just that row, then drops any resulting fragment that is
        empty or negligibly small next to another part sharing the same original attributes — those are
        reconstruction artifacts, not real features. If two or more parts survive with real, comparable
        size, they're merged back into a single multipart feature instead of being left as duplicate rows.
        This only ever applies to rows the repair touched — a pre-existing multipart feature that was
        simply copied through unchanged (e.g. a barangay with a legitimate offshore island) is left
        completely alone, even elsewhere in the same output layer. All of this is logged.
        </p>

        <h3>If One Feature Has Multiple Error Types</h3>
        <p>
        Some features may have more than one geometry problem. In this case, after Repair Selected Features
        finishes, scan the resulting temporary output layer(s) again with <b>Scan Layers</b> to check for
        any remaining errors, and repeat the repair as needed.
        </p>

        <h3>Output Layers</h3>
        <p>
        Invalid, Wrong-type, Self Intersection, and Null/Empty repairs all create temporary memory layers;
        the source layer is never modified.
        The temporary output keeps the same original attribute fields so it can be exported more easily.
        Recovery status, method, and notes are shown in the log instead of being added as extra fields.
        Re-run Scan Layers on the temporary output afterward to confirm no errors remain.
        </p>

        <h3>Review and Limitations</h3>
        <ul>
            <li>Always visually inspect the temporary output layer.</li>
            <li>Try to run Check Validity again on the temporary output layer.</li>
            <li>Deleted feature records cannot be recovered by this tool.</li>
            <li>Edge polygons cannot be safely reconstructed when the outer boundary is unknown.</li>
            <li>If a missing edge polygon cannot be recovered, return it to the LGU for corrected boundary geometry.</li>
            <li>Some complex errors may still require manual review (Duplicate Geometry, Dangle).</li>
        </ul>

        <h3>Log Information</h3>
        <p>
        The log shows which layer and feature ID were processed, plus the repair result when applicable.
        For Null / Empty / Missing fixes, recovery status, method, and notes are written in the log.
        </p>

        <hr>

        <p align="center">
        <b>Geometry Repair Toolkit</b><br>
        Version 1.2.1<br>
        Build 2026.07 <br><br>
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
        self.setWindowTitle("Geometry Repair Toolkit")
        self.resize(1100, 720)
        self._build()

    def closeEvent(self, event):
        # The checker tab can leave a red outline/X marker on the map canvas
        # (from double-clicking an error row) — make sure those are removed
        # when the dialog closes, not just when Clear is pressed.
        try:
            self.checker_tab._clear_error_highlight()
        except Exception:
            pass
        super().closeEvent(event)

    def reject(self):
        # Covers the Esc-key path, which doesn't always go through
        # closeEvent().
        try:
            self.checker_tab._clear_error_highlight()
        except Exception:
            pass
        super().reject()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10); root.setSpacing(6)

        title = QLabel("Geometry Repair Toolkit")
        title.setStyleSheet("font-size:16px; font-weight:700; padding:2px 0;")
        root.addWidget(title)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setStyleSheet("color:#bdbdbd;")
        root.addWidget(sep)

        tabs = QTabWidget()

        self.checker_tab = CheckerTab()
        self.help_tab = HelpInfoTab()

        tabs.addTab(self.checker_tab, "Geometry Fixer")
        tabs.addTab(self.help_tab, "Help and Information")

        root.addWidget(tabs, stretch=1)


dlg = GeometryToolkit()
dlg.show()