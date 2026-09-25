from __future__ import annotations

import json
import sqlite3
from typing import Any

JSON_SUFFIX = "_json"


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out: dict[str, Any] = {}
    for key, value in zip(row.keys(), tuple(row), strict=True):
        if key.endswith(JSON_SUFFIX):
            name = key[: -len(JSON_SUFFIX)]
            out[name] = json.loads(value) if value else None
        else:
            out[key] = value
    return out


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [d for d in (row_to_dict(r) for r in rows) if d is not None]


def as_bool(value: Any) -> bool:
    return bool(int(value)) if value is not None else False
