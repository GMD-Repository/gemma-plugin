from typing import Any
from qgis.PyQt.QtCore import QCoreApplication, QThread

_TOTAL_PHASES = 8
_PHASE_LABELS = [
    "Phase 1/8: Initializing",
    "Phase 2/8: Scanning Candidates & Matching Buildings",
    "Phase 3/8: Indexing Roads & Rivers",
    "Phase 4/8: Loading EAs",
    "Phase 5/8: Splitting EAs",
    "Phase 6/8: Merging EAs",
    "Phase 7/8: Compliance Sweep",
    "Phase 8/8: Writing Output",
]

def yield_to_ui(counter: int, interval: int = 250) -> None:
    """Yield to Qt event loop periodically so GUI remains responsive."""
    if counter % interval == 0:
        if QThread.currentThread() == QCoreApplication.instance().thread():
            QCoreApplication.processEvents()
