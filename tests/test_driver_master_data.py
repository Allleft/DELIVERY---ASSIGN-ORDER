from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path


class DriverMasterDataTest(unittest.TestCase):
    def test_sample_drivers_match_raw_driver_master_rows(self) -> None:
        raw_rows = {}
        with Path("data/raw/driver-raw-data.csv").open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                license_no = (row.get("license_no") or "").strip()
                if license_no:
                    raw_rows[license_no] = row

        sample = json.loads(Path("examples/sample-dispatch-input.json").read_text(encoding="utf-8"))
        drivers = sample["drivers"]
        self.assertEqual(len(raw_rows), len(drivers))

        sample_license_set = {driver["metadata"]["license_no"] for driver in drivers}
        self.assertEqual(set(raw_rows), sample_license_set)

        for driver in drivers:
            license_no = driver["metadata"]["license_no"]
            raw = raw_rows[license_no]
            self.assertEqual(raw["name"], driver["metadata"]["name"])
            self.assertEqual(raw["email"] or None, driver["metadata"]["email"])
            self.assertEqual(raw["phone_number"] or None, driver["metadata"]["phone_number"])
            self.assertEqual("driver master export", driver["metadata"]["source"])

            self.assertEqual("08:00", driver["shift_start"])
            self.assertEqual("17:00", driver["shift_end"])
            self.assertTrue(driver["is_available"])
            self.assertEqual([], driver["preferred_zone_codes"])
            self.assertEqual([], driver["historical_vehicle_ids"])

            expected_branch = (raw["branch_no"] or "").strip() or "MEL"
            expected_start = (raw["default_start_location"] or "").strip() or "Depot"
            expected_end = (raw["default_end_location"] or "").strip() or "Depot"
            self.assertEqual(expected_branch, driver["branch_no"])
            self.assertEqual(expected_start, driver["start_location"])
            self.assertEqual(expected_end, driver["end_location"])


if __name__ == "__main__":
    unittest.main()
