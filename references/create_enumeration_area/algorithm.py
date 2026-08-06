"""
Create Enumeration Areas Processing Algorithm
Re-exports EADMCandidatesAlgorithm from eadm_candidates as CreateEAAlgorithm
for QGIS Processing Provider compatibility.
"""

from .eadm_candidates import EADMCandidatesAlgorithm as CreateEAAlgorithm, TablePreviewWidgetWrapper

__all__ = ["CreateEAAlgorithm", "TablePreviewWidgetWrapper"]
