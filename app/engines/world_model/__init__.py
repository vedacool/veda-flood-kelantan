"""Meterless World Model engine (Python implementation for VEDA)."""
from app.engines.world_model.resolve import decide, name_similarity
from app.engines.world_model.stable_ids import entity_id_from_name, external_id, normalize_name
from app.engines.world_model.world import ProvenanceError, WorldModel

__all__ = ["WorldModel", "ProvenanceError", "decide", "name_similarity", "entity_id_from_name", "external_id",
           "normalize_name"]
