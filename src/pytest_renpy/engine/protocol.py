"""JSON-lines protocol for IPC between pytest and the Ren'Py engine.

Commands flow from pytest (client) to the engine (server).
Responses flow from the engine back to pytest.
Both are serialized as newline-delimited JSON.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Command:
    cmd: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {"cmd": self.cmd}
        d.update(self.payload)
        return d


@dataclass
class Response:
    status: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {"status": self.status}
        d.update(self.data)
        return d


def serialize(obj: dict[str, Any]) -> str:
    return json.dumps(obj, default=_fallback_serializer) + "\n"


def deserialize(line: str) -> dict[str, Any]:
    return json.loads(line)


def _fallback_serializer(obj: Any) -> dict[str, str]:
    return {"_type": type(obj).__name__, "_repr": repr(obj)}


def serialize_value(val: Any) -> Any:
    try:
        json.dumps(val)
        return val
    except (TypeError, ValueError):
        return _fallback_serializer(val)
