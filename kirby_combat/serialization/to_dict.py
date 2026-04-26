"""Convert engine objects to JSON-safe dicts.

Every output dict includes `__type__` discriminator for from_dict to dispatch.
Primitives pass through unchanged. Enum values emit `.value`. Sets emit as lists.
Tuples emit as lists (JSON has no tuple). Datetimes emit as ISO strings.
"""
from __future__ import annotations

from dataclasses import is_dataclass, fields
from datetime import datetime
from enum import Enum
from typing import Any


def to_dict(obj: Any) -> Any:
    """Recursively convert to JSON-safe shape."""
    if obj is None or isinstance(obj, (int, float, str, bool)):
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (list, tuple)):
        return [to_dict(x) for x in obj]
    if isinstance(obj, set) or isinstance(obj, frozenset):
        return sorted([to_dict(x) for x in obj], key=str)
    if isinstance(obj, dict):
        return {str(k): to_dict(v) for k, v in obj.items()}
    if is_dataclass(obj):
        result: dict[str, Any] = {"__type__": type(obj).__name__}
        for f in fields(obj):
            result[f.name] = to_dict(getattr(obj, f.name))
        return result
    # Fallback: try vars()
    if hasattr(obj, "__dict__"):
        result = {"__type__": type(obj).__name__}
        for k, v in vars(obj).items():
            if not k.startswith("_"):
                result[k] = to_dict(v)
        return result
    raise TypeError(f"cannot serialize {type(obj).__name__}")
