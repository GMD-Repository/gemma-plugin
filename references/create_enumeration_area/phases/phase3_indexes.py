from qgis.core import (
    QgsSpatialIndex,
    QgsProcessingException,
)
from ..helpers.constants import _PHASE_LABELS, yield_to_ui


def run_phase_3(alg, parameters, context, feedback, multi_feedback, p1, p2):
    """
    Executes Phase 3 (Indexing Roads & Rivers), including:
    - Re-using candidate-only spatial index of starting EAs built in Phase 2
    - Building spatial index for Road layer (if provided)
    - Building spatial index for River layer (if provided)

    Returns state dictionary containing road and river indexes and geometry maps.
    """
    road_source = p1["road_source"]
    river_source = p1["river_source"]
    temp_ea_index = p2["temp_ea_index"]
    temp_ea_by_id = p2["temp_ea_by_id"]

    multi_feedback.setCurrentStep(2)
    multi_feedback.setProgressText(f"{_PHASE_LABELS[2]}...")
    feedback.pushInfo("Phase 3/8: Building spatial indexes (barangay, road, river, candidate EAs only)...")

    # Re-use candidate-only spatial index of starting EAs built in Phase 2
    feedback.pushInfo("Re-using candidate-only spatial index of starting EAs built in Phase 2...")
    ea_index = temp_ea_index
    ea_by_id = temp_ea_by_id

    road_index = None
    road_geoms = {}
    if road_source is not None:
        feedback.pushInfo("Building spatial index of Road Layer...")
        road_index = QgsSpatialIndex()
        for idx, feat in enumerate(road_source.getFeatures()):
            if multi_feedback.isCanceled():
                raise QgsProcessingException("Algorithm cancelled by user.")
            yield_to_ui(idx)
            road_index.insertFeature(feat)
            road_geoms[feat.id()] = feat.geometry()

    river_index = None
    river_geoms = {}
    if river_source is not None:
        feedback.pushInfo("Building spatial index of River Layer...")
        river_index = QgsSpatialIndex()
        for idx, feat in enumerate(river_source.getFeatures()):
            if multi_feedback.isCanceled():
                raise QgsProcessingException("Algorithm cancelled by user.")
            yield_to_ui(idx)
            river_index.insertFeature(feat)
            river_geoms[feat.id()] = feat.geometry()

    multi_feedback.setProgress(100)

    return {
        "ea_index": ea_index,
        "ea_by_id": ea_by_id,
        "road_index": road_index,
        "road_geoms": road_geoms,
        "river_index": river_index,
        "river_geoms": river_geoms,
    }
