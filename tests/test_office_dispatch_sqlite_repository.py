from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from backend.db.sqlite_repository import SQLiteDispatchRepository
from backend.services.dispatch_service import DispatchBatchService
from backend.services.geocoding import StaticAddressGeocoder


class SQLiteDispatchRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._temp_dir.name) / "office-dispatch.sqlite3"
        self.repo = SQLiteDispatchRepository(self.db_path)

    def tearDown(self) -> None:
        self.repo.close()
        self._temp_dir.cleanup()

    def test_create_list_get_batch_persists(self) -> None:
        created = self.repo.create_batch("2026-05-10", created_by="sqlite.user", notes="sqlite-batch")
        listed = self.repo.list_batches()
        loaded = self.repo.get_batch(int(created["batch_id"]))

        self.assertEqual("DRAFT", created["status"])
        self.assertEqual(1, len(listed))
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual("2026-05-10", loaded["dispatch_date"])

    def test_replace_and_list_orders_persists(self) -> None:
        batch = self.repo.create_batch("2026-05-10", created_by="sqlite.user")
        batch_id = int(batch["batch_id"])
        self.repo.replace_batch_orders(batch_id, [self._order(order_id=2001), self._order(order_id="2002A")])

        loaded = self.repo.list_batch_orders(batch_id)
        self.assertEqual(2, len(loaded))
        self.assertEqual({2001, "2002A"}, {row["order_id"] for row in loaded})

    def test_save_and_get_generated_results(self) -> None:
        batch = self.repo.create_batch("2026-05-10", created_by="sqlite.user")
        batch_id = int(batch["batch_id"])
        payload = {
            "plans": [{"plan_id": "PLAN-1"}],
            "order_assignments": [{"order_id": 2001, "plan_id": "PLAN-1"}],
            "exceptions": [],
        }
        self.repo.save_generated_results(batch_id, payload)

        loaded = self.repo.get_generated_results(batch_id)
        self.assertEqual(payload, loaded)

    def test_clear_generated_results_resets_payload(self) -> None:
        batch = self.repo.create_batch("2026-05-10", created_by="sqlite.user")
        batch_id = int(batch["batch_id"])
        self.repo.save_generated_results(
            batch_id,
            {"plans": [{"plan_id": "PLAN-1"}], "order_assignments": [{"order_id": 1}], "exceptions": [{"reason_code": "X"}]},
        )

        self.repo.clear_generated_results(batch_id)
        loaded = self.repo.get_generated_results(batch_id)

        self.assertEqual({"plans": [], "order_assignments": [], "exceptions": []}, loaded)

    def test_reopen_same_db_path_preserves_batches_orders_and_results(self) -> None:
        batch = self.repo.create_batch("2026-05-10", created_by="sqlite.user")
        batch_id = int(batch["batch_id"])
        self.repo.replace_batch_orders(batch_id, [self._order(order_id=3001)])
        self.repo.save_generated_results(
            batch_id,
            {"plans": [{"plan_id": "PLAN-3001"}], "order_assignments": [{"order_id": 3001}], "exceptions": []},
        )
        self.repo.close()

        reopened = SQLiteDispatchRepository(self.db_path)
        try:
            loaded_batch = reopened.get_batch(batch_id)
            loaded_orders = reopened.list_batch_orders(batch_id)
            loaded_results = reopened.get_generated_results(batch_id)
        finally:
            reopened.close()

        self.assertIsNotNone(loaded_batch)
        self.assertEqual(1, len(loaded_orders))
        self.assertEqual({"plans", "order_assignments", "exceptions"}, set(loaded_results.keys()))
        self.repo = SQLiteDispatchRepository(self.db_path)

    def test_list_active_resources_returns_seeded_availability(self) -> None:
        self.repo.seed_driver(self._driver(driver_id=1, is_available=True))
        self.repo.seed_driver(self._driver(driver_id=2, is_available=False))
        self.repo.seed_vehicle(self._vehicle(vehicle_id=101, is_available=True))
        self.repo.seed_vehicle(self._vehicle(vehicle_id=102, is_available=False))

        active_drivers = self.repo.list_active_drivers()
        active_vehicles = self.repo.list_active_vehicles()

        self.assertEqual([1], [row["driver_id"] for row in active_drivers])
        self.assertEqual([101], [row["vehicle_id"] for row in active_vehicles])

    def test_replace_and_list_drivers_and_vehicles_persist(self) -> None:
        self.repo.replace_drivers(
            [
                self._driver(driver_id=31, is_available=True),
                self._driver(driver_id=32, is_available=False),
            ]
        )
        self.repo.replace_vehicles(
            [
                self._vehicle(vehicle_id=401, is_available=True),
                self._vehicle(vehicle_id=402, is_available=False),
            ]
        )

        self.assertEqual([31, 32], [row["driver_id"] for row in self.repo.list_drivers()])
        self.assertEqual([401, 402], [row["vehicle_id"] for row in self.repo.list_vehicles()])
        self.assertEqual([31], [row["driver_id"] for row in self.repo.list_active_drivers()])
        self.assertEqual([401], [row["vehicle_id"] for row in self.repo.list_active_vehicles()])

    def test_dispatch_batch_service_generates_with_sqlite_repo(self) -> None:
        service = DispatchBatchService(repository=self.repo)
        batch = service.create_dispatch_batch("2026-05-10", created_by="sqlite.user")
        batch_id = int(batch["batch_id"])
        self.repo.seed_driver(self._driver(driver_id=11, is_available=True))
        self.repo.seed_vehicle(self._vehicle(vehicle_id=211, is_available=True))
        service.save_batch_orders(batch_id, [self._order(order_id=9001), self._order(order_id=9002, urgency="URGENT")])

        result = service.generate_dispatch_for_batch(batch_id)

        self.assertEqual({"plans", "order_assignments", "exceptions"}, set(result.keys()))
        self.assertEqual("GENERATED", service.get_dispatch_batch(batch_id)["status"])

    def test_sqlite_persists_resolved_coordinates_after_reopen(self) -> None:
        geocoder = StaticAddressGeocoder(
            mapping={
                "Depot": (-37.7800, 144.9300),
                "98-102 Hume Hwy, Somerton VIC 3062, Australia": (-37.6461, 144.9525),
            }
        )
        service = DispatchBatchService(repository=self.repo, address_geocoder=geocoder)
        batch = service.create_dispatch_batch("2026-05-12", created_by="sqlite.user")
        batch_id = int(batch["batch_id"])
        self.repo.seed_driver(self._driver(driver_id=66, is_available=True, with_coordinates=False))
        self.repo.seed_vehicle(self._vehicle(vehicle_id=266, is_available=True))
        service.save_batch_orders(batch_id, [self._order(order_id=9201, with_coordinates=False)])
        service.generate_dispatch_for_batch(batch_id)

        self.repo.close()
        reopened = SQLiteDispatchRepository(self.db_path)
        try:
            persisted_order = reopened.list_batch_orders(batch_id)[0]
            persisted_driver = reopened.list_drivers()[0]
        finally:
            reopened.close()
        self.repo = SQLiteDispatchRepository(self.db_path)

        self.assertAlmostEqual(-37.6461, float(persisted_order["lat"]), places=4)
        self.assertAlmostEqual(144.9525, float(persisted_order["lng"]), places=4)
        self.assertAlmostEqual(-37.7800, float(persisted_driver["start_lat"]), places=4)
        self.assertAlmostEqual(144.9300, float(persisted_driver["start_lng"]), places=4)

    @staticmethod
    def _order(order_id: int | str, urgency: str = "NORMAL", with_coordinates: bool = True) -> dict[str, Any]:
        lat = -37.8136 if with_coordinates else None
        lng = 144.9631 if with_coordinates else None
        address = f"Order-{order_id} Address" if with_coordinates else "98-102 Hume Hwy, Somerton VIC 3062, Australia"
        return {
            "order_id": order_id,
            "dispatch_date": "2026-05-10",
            "delivery_address": address,
            "lat": lat,
            "lng": lng,
            "zone_code": "LOCAL",
            "urgency": urgency,
            "window_start": "08:00",
            "window_end": "12:00",
            "designated_driver_id": None,
            "load_type": "MIXED",
            "kg_count": 7.5,
            "pallet_count": 1,
            "bag_count": 2,
            "postcode": "3000",
            "suburb": "Melbourne",
            "metadata": {},
        }

    @staticmethod
    def _driver(driver_id: int, is_available: bool, with_coordinates: bool = True) -> dict[str, Any]:
        start_lat = -37.8100 if with_coordinates else None
        start_lng = 144.9600 if with_coordinates else None
        end_lat = -37.8100 if with_coordinates else None
        end_lng = 144.9600 if with_coordinates else None
        return {
            "driver_id": driver_id,
            "shift_start": "07:00",
            "shift_end": "17:00",
            "is_available": is_available,
            "start_location": "Depot",
            "end_location": "Depot",
            "preferred_zone_codes": ["LOCAL"],
            "historical_vehicle_ids": [],
            "branch_no": None,
            "start_lat": start_lat,
            "start_lng": start_lng,
            "end_lat": end_lat,
            "end_lng": end_lng,
            "metadata": {"name": f"Driver {driver_id}"},
        }

    @staticmethod
    def _vehicle(vehicle_id: int, is_available: bool) -> dict[str, Any]:
        return {
            "vehicle_id": vehicle_id,
            "vehicle_type": "van",
            "is_available": is_available,
            "kg_capacity": 1000.0,
            "pallet_capacity": 6,
            "tub_capacity": 12,
            "trolley_capacity": 4,
            "stillage_capacity": 2,
            "loose_capacity": None,
            "metadata": {"rego": f"REGO-{vehicle_id}"},
        }


if __name__ == "__main__":
    unittest.main()
