from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path


class VehicleMasterDataTest(unittest.TestCase):
    def test_sample_vehicles_match_raw_vehicle_master_rows(self) -> None:
        raw_rows = {}
        with Path("data/raw/vehicle-raw-data.csv").open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                raw_rows[row["rego"]] = row

        sample = json.loads(Path("examples/sample-dispatch-input.json").read_text(encoding="utf-8"))
        self.assertEqual(len(raw_rows), len(sample["vehicles"]))
        self.assertEqual(
            set(raw_rows),
            {vehicle["metadata"]["rego"] for vehicle in sample["vehicles"]},
        )

        for vehicle in sample["vehicles"]:
            rego = vehicle["metadata"]["rego"]
            self.assertIn(rego, raw_rows)
            raw = raw_rows[rego]
            self.assertEqual(raw["vehicle_type"], vehicle["vehicle_type"])
            self.assertEqual(int(raw["pallet_capacity"] or 0), vehicle["pallet_capacity"])
            self.assertEqual(int(raw["tub_capacity"] or 0), vehicle["tub_capacity"])
            self.assertEqual(int(raw["trolley_capacity"] or 0), vehicle.get("trolley_capacity", 0))
            self.assertEqual(int(raw["stillage_capacity"] or 0), vehicle.get("stillage_capacity", 0))
            self.assertEqual(0, vehicle["kg_capacity"])
            self.assertEqual(int(raw["shelf_count"] or 0), vehicle["metadata"].get("shelf_count", 0))
            self.assertEqual(raw["capacity"] or None, vehicle["metadata"].get("raw_capacity"))
            self.assertEqual(raw["fuel_card_shell"] or None, vehicle["metadata"].get("fuel_card_shell"))
            self.assertEqual(raw["fuel_card_bp_plus"] or None, vehicle["metadata"].get("fuel_card_bp_plus"))
            self.assertEqual(raw["linkt_ref"] or None, vehicle["metadata"].get("linkt_ref"))
            self.assertEqual(raw["service_period"] or None, vehicle["metadata"].get("service_period"))


if __name__ == "__main__":
    unittest.main()
