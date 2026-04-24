from __future__ import annotations

import argparse
import copy
import csv
import json
from pathlib import Path
from typing import Any


ALLOWED_CHANGED_TOP_LEVEL_KEYS = {"drivers", "vehicles"}


def _text_or_none(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _text_or_default(value: str | None, default: str) -> str:
    text = (value or "").strip()
    return text or default


def _int_or_default(value: str | None, default: int = 0) -> int:
    text = (value or "").strip()
    if text == "":
        return default
    try:
        return int(float(text))
    except ValueError:
        return default


def _dedupe_last(rows: list[dict[str, str]], key_field: str) -> list[dict[str, str]]:
    keyed_rows: dict[str, dict[str, str]] = {}
    key_order: list[str] = []
    for row in rows:
        key = (row.get(key_field) or "").strip()
        if key == "":
            continue
        if key in keyed_rows:
            key_order.remove(key)
        keyed_rows[key] = row
        key_order.append(key)
    return [keyed_rows[key] for key in key_order]


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build_drivers_from_raw(path: Path) -> list[dict[str, Any]]:
    rows = _dedupe_last(_read_csv_rows(path), "license_no")
    drivers: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        name = _text_or_none(row.get("name"))
        license_no = _text_or_none(row.get("license_no"))
        if name is None or license_no is None:
            continue
        branch_no = _text_or_default(row.get("branch_no"), "MEL")
        start_location = _text_or_default(row.get("default_start_location"), "Depot")
        end_location = _text_or_default(row.get("default_end_location"), "Depot")
        drivers.append(
            {
                "driver_id": index,
                "shift_start": "08:00",
                "shift_end": "17:00",
                "is_available": True,
                "start_location": start_location,
                "end_location": end_location,
                "preferred_zone_codes": [],
                "historical_vehicle_ids": [],
                "branch_no": branch_no,
                "metadata": {
                    "name": name,
                    "license_no": license_no,
                    "email": _text_or_none(row.get("email")),
                    "phone_number": _text_or_none(row.get("phone_number")),
                    "source": "driver master export",
                },
            }
        )
    return drivers


def build_vehicles_from_raw(path: Path) -> list[dict[str, Any]]:
    rows = _dedupe_last(_read_csv_rows(path), "rego")
    vehicles: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        rego = _text_or_none(row.get("rego"))
        vehicle_type = _text_or_none(row.get("vehicle_type"))
        if rego is None or vehicle_type is None:
            continue
        vehicles.append(
            {
                "vehicle_id": index,
                "vehicle_type": vehicle_type,
                "is_available": True,
                "kg_capacity": 0,
                "pallet_capacity": _int_or_default(row.get("pallet_capacity"), 0),
                "tub_capacity": _int_or_default(row.get("tub_capacity"), 0),
                "trolley_capacity": _int_or_default(row.get("trolley_capacity"), 0),
                "stillage_capacity": _int_or_default(row.get("stillage_capacity"), 0),
                "metadata": {
                    "rego": rego,
                    "source": "vehicle master export",
                    "raw_capacity": _text_or_none(row.get("capacity")),
                    "shelf_count": _int_or_default(row.get("shelf_count"), 0),
                    "fuel_card_shell": _text_or_none(row.get("fuel_card_shell")),
                    "fuel_card_bp_plus": _text_or_none(row.get("fuel_card_bp_plus")),
                    "linkt_ref": _text_or_none(row.get("linkt_ref")),
                    "service_period": _text_or_none(row.get("service_period")),
                },
            }
        )
    return vehicles


def changed_top_level_keys(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    keys = set(before) | set(after)
    return {key for key in keys if before.get(key) != after.get(key)}


def assert_only_allowed_top_level_changes(
    before: dict[str, Any],
    after: dict[str, Any],
    allowed_keys: set[str] | None = None,
) -> set[str]:
    allowed = allowed_keys or ALLOWED_CHANGED_TOP_LEVEL_KEYS
    changed = changed_top_level_keys(before, after)
    disallowed = changed - allowed
    if disallowed:
        disallowed_text = ", ".join(sorted(disallowed))
        raise RuntimeError(f"Unexpected top-level changes detected: {disallowed_text}")
    return changed


def refresh_sample_master_data(
    sample_path: Path,
    driver_raw_path: Path,
    vehicle_raw_path: Path,
) -> set[str]:
    original = json.loads(sample_path.read_text(encoding="utf-8"))
    updated = copy.deepcopy(original)
    updated["drivers"] = build_drivers_from_raw(driver_raw_path)
    updated["vehicles"] = build_vehicles_from_raw(vehicle_raw_path)
    changed = assert_only_allowed_top_level_changes(original, updated)
    if not changed:
        return changed
    sample_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh sample drivers/vehicles from raw CSV sources without touching orders/config."
    )
    parser.add_argument(
        "--sample",
        default="examples/sample-dispatch-input.json",
        help="Path to sample dispatch input JSON.",
    )
    parser.add_argument(
        "--driver-raw",
        default="data/raw/driver-raw-data.csv",
        help="Path to driver raw CSV.",
    )
    parser.add_argument(
        "--vehicle-raw",
        default="data/raw/vehicle-raw-data.csv",
        help="Path to vehicle raw CSV.",
    )
    args = parser.parse_args()

    changed = refresh_sample_master_data(
        sample_path=Path(args.sample),
        driver_raw_path=Path(args.driver_raw),
        vehicle_raw_path=Path(args.vehicle_raw),
    )
    changed_text = ", ".join(sorted(changed)) if changed else "none"
    print(f"Updated top-level keys: {changed_text}")


if __name__ == "__main__":
    main()
