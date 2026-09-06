# -*- coding: utf-8 -*-
import os
from qgis.core import QgsProject
from qgis.PyQt.QtCore import Qt


def show_cbmsmv_dialog(iface, offline_editing=None, on_finished_callback=None):
    try:
        from ...references.cbms_mv.cbmsmv_dialog import CbmsmvDialog
    except (ImportError, ValueError):
        try:
            from ..references.cbms_mv.cbmsmv_dialog import CbmsmvDialog
        except (ImportError, ValueError):
            import sys
            plugin_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            if plugin_dir not in sys.path:
                sys.path.insert(0, plugin_dir)
            from references.cbms_mv.cbmsmv_dialog import CbmsmvDialog

    push_dlg = CbmsmvDialog(
        iface,
        QgsProject.instance(),
        offline_editing,
        iface.mainWindow() if iface else None,
    )
    push_dlg.setAttribute(Qt.WA_DeleteOnClose)
    push_dlg.setWindowFlags(Qt.Dialog)

    push_dlg.show()
    push_dlg.raise_()
    push_dlg.activateWindow()

    if on_finished_callback:
        push_dlg.finished.connect(on_finished_callback)

    return push_dlg
