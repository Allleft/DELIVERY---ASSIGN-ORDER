"""Static address geocoding helpers for Office Dispatch backend."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol


class AddressGeocoder(Protocol):
    def geocode(self, address: str) -> dict[str, float] | None: ...


_SPACE_PATTERN = re.compile(r"\s+")


def normalize_address_key(text: str) -> str:
    normalized = _SPACE_PATTERN.sub(" ", str(text or "").strip().lower())
    return normalized


class StaticAddressGeocoder:
    """Address geocoder backed by static dictionary and optional JSON file."""

    def __init__(
        self,
        mapping: dict[str, Any] | None = None,
        json_path: str | Path | None = None,
    ) -> None:
        self._mapping: dict[str, dict[str, float]] = {}
        self._load_mapping(mapping or {})
        if json_path is not None:
            self._load_json_file(json_path)

    def geocode(self, address: str) -> dict[str, float] | None:
        key = normalize_address_key(address)
        if key == "":
            return None
        point = self._mapping.get(key)
        if point is None:
            return None
        return {"lat": float(point["lat"]), "lng": float(point["lng"])}

    def _load_json_file(self, json_path: str | Path) -> None:
        path = Path(json_path)
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(payload, dict):
            self._load_mapping(payload)

    def _load_mapping(self, mapping: dict[str, Any]) -> None:
        for raw_key, raw_value in mapping.items():
            key = normalize_address_key(raw_key)
            point = _normalize_point(raw_value)
            if key == "" or point is None:
                continue
            self._mapping[key] = point


def _normalize_point(value: Any) -> dict[str, float] | None:
    if isinstance(value, dict):
        lat = value.get("lat")
        lng = value.get("lng")
        if _is_number(lat) and _is_number(lng):
            return {"lat": float(lat), "lng": float(lng)}
        return None
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        lat = value[0]
        lng = value[1]
        if _is_number(lat) and _is_number(lng):
            return {"lat": float(lat), "lng": float(lng)}
    return None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
