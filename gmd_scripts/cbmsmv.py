import os
from qgis.core import QgsProject
from qgis.PyQt.QtCore import Qt

def show_cbmsmv_dialog(iface, offline_editing=None, on_finished_callback=None):
    from ..references.cbmsmv.cbmsmv_dialog import CbmsmvDialog
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

