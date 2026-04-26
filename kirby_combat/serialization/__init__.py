"""Serialize/deserialize engine objects for persistence and transport."""
from kirby_combat.serialization.to_dict import to_dict
from kirby_combat.serialization.from_dict import from_dict

__all__ = ["to_dict", "from_dict"]
