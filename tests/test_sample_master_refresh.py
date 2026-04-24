from __future__ import annotations

import csv
import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from tools.refresh_sample_master_data import (
    assert_only_allowed_top_level_changes,
    refresh_sample_master_data,
)


class SampleMasterRefreshTest(unittest.TestCase):
    def test_refresh_updates_only_drivers_and_vehicles(self) -> None:
        tmp_root = Path("tests/.tmp")
        tmp_root.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_root / f"sample-master-refresh-{uuid4().hex}"
        tmp_path.mkdir(parents=True, exist_ok=False)
        try:
            sample_path = tmp_path / "sample.json"
            driver_raw_path = tmp_path / "driver-raw.csv"
            vehicle_raw_path = tmp_path / "vehicle-raw.csv"

            sample_payload = {
                "config": {"zone_by_postcode": {"3000": "LOCAL"}, "manual_flag": "KEEP_ME"},
                "orders": [{"order_id": 1, "delivery_address": "Alpha"}],
                "drivers": [{"driver_id": 99}],
                "vehicles": [{"vehicle_id": 99}],
                "other_manual_notes": {"owner": "business"},
            }
            sample_path.write_text(json.dumps(sample_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            self._write_csv(
                driver_raw_path,
                [
                    {
                        "name": "Alice Driver",
                        "license_no": "LIC001",
                        "email": "alice@example.com",
                        "phone_number": "0400000000",
                        "branch_no": "",
                        "default_start_location": "",
                        "default_end_location": "",
                    }
                ],
            )
            self._write_csv(
                vehicle_raw_path,
                [
                    {
                        "rego": "ABC123",
                        "vehicle_type": "van",
                        "capacity": "",
                        "tub_capacity": "6",
                        "pallet_capacity": "3",
                        "trolley_capacity": "1",
                        "stillage_capacity": "0",
                        "shelf_count": "0",
                        "fuel_card_shell": "",
                        "fuel_card_bp_plus": "",
                        "linkt_ref": "",
                        "service_period": "",
                    }
                ],
            )

            changed = refresh_sample_master_data(sample_path, driver_raw_path, vehicle_raw_path)
            self.assertEqual({"drivers", "vehicles"}, changed)

            refreshed = json.loads(sample_path.read_text(encoding="utf-8"))
            self.assertEqual(sample_payload["config"], refreshed["config"])
            self.assertEqual(sample_payload["orders"], refreshed["orders"])
            self.assertEqual(sample_payload["other_manual_notes"], refreshed["other_manual_notes"])

            self.assertEqual(1, len(refreshed["drivers"]))
            driver = refreshed["drivers"][0]
            self.assertEqual("08:00", driver["shift_start"])
            self.assertEqual("17:00", driver["shift_end"])
            self.assertTrue(driver["is_available"])
            self.assertEqual("MEL", driver["branch_no"])
            self.assertEqual("Depot", driver["start_location"])
            self.assertEqual("Depot", driver["end_location"])
            self.assertEqual([], driver["preferred_zone_codes"])
            self.assertEqual([], driver["historical_vehicle_ids"])
            self.assertEqual("LIC001", driver["metadata"]["license_no"])

            self.assertEqual(1, len(refreshed["vehicles"]))
            vehicle = refreshed["vehicles"][0]
            self.assertEqual("ABC123", vehicle["metadata"]["rego"])
            self.assertEqual("van", vehicle["vehicle_type"])
            self.assertEqual(0, vehicle["kg_capacity"])
            self.assertEqual(3, vehicle["pallet_capacity"])
            self.assertEqual(6, vehicle["tub_capacity"])
        finally:
            shutil.rmtree(tmp_path, ignore_errors=True)

    def test_guard_raises_when_non_allowed_key_changes(self) -> None:
        before = {"config": {"k": 1}, "orders": [1], "drivers": [], "vehicles": []}
        after = {"config": {"k": 2}, "orders": [1], "drivers": [], "vehicles": []}
        with self.assertRaises(RuntimeError):
            assert_only_allowed_top_level_changes(before, after)

    @staticmethod
    def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
        fieldnames = list(rows[0].keys()) if rows else []
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)


if __name__ == "__main__":
    unittest.main()
