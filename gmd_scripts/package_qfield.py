import os
from qgis.core import QgsProject
from qgis.PyQt.QtCore import Qt

def show_package_dialog(iface, offline_editing, on_finished_callback=None):
    from ..references.gui.package_dialog import PackageDialog
    push_dlg = PackageDialog(
        iface,
        QgsProject.instance(),
        offline_editing,
        iface.mainWindow(),
    )
    push_dlg.setAttribute(Qt.WA_DeleteOnClose)
    push_dlg.setWindowFlags(Qt.Dialog)

    push_dlg.show()

    if on_finished_callback:
        push_dlg.finished.connect(on_finished_callback)

    return push_dlg
