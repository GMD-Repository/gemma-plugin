"""
Create Enumeration Areas Processing Algorithm
Re-exports EADMCandidatesAlgorithm from eadm_candidates as CreateEAAlgorithm
and TablePreviewWidgetWrapper from preview_widget
for QGIS Processing Provider compatibility.
"""

from .eadm_candidates import EADMCandidatesAlgorithm as CreateEAAlgorithm
from .preview_widget import TablePreviewWidgetWrapper

__all__ = ["CreateEAAlgorithm", "TablePreviewWidgetWrapper"]
