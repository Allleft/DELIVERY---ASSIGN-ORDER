from __future__ import annotations

import unittest
from datetime import date

from backend.db.repository import InMemoryDispatchRepository
from backend.services.dispatch_service import DispatchBatchService
from backend.services.geocoding import StaticAddressGeocoder


class OfficeDispatchServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = InMemoryDispatchRepository()
        self.service = DispatchBatchService(repository=self.repo)

    def test_create_dispatch_batch(self) -> None:
        batch = self.service.create_dispatch_batch("2026-05-01", created_by="office.user", notes="phase2a")

        self.assertEqual("DRAFT", batch["status"])
        self.assertEqual("2026-05-01", batch["dispatch_date"])
        listed = self.service.list_dispatch_batches()
        self.assertEqual(1, len(listed))
        self.assertEqual(batch["batch_id"], listed[0]["batch_id"])

    def test_save_and_load_manual_orders(self) -> None:
        batch = self.service.create_dispatch_batch("2026-05-01", created_by="office.user")
        batch_id = int(batch["batch_id"])

        saved = self.service.save_batch_orders(batch_id, [self._order(order_id=2001), self._order(order_id="2002A")])
        loaded = self.service.list_batch_orders(batch_id)

        self.assertEqual(2, len(saved))
        self.assertEqual(2, len(loaded))
        loaded_ids = {row["order_id"] for row in loaded}
        self.assertEqual({2001, "2002A"}, loaded_ids)

    def test_save_and_list_drivers_and_vehicles(self) -> None:
        saved_drivers = self.service.save_drivers(
            [
                self._driver(driver_id=20, preferred_zone_codes=("LOCAL",)),
                self._driver(driver_id=21, preferred_zone_codes=("WEST",)),
            ]
        )
        saved_vehicles = self.service.save_vehicles(
            [
                self._vehicle(vehicle_id=220, rego="2AAA00"),
                self._vehicle(vehicle_id=221, rego="2BBB00"),
            ]
        )

        listed_drivers = self.service.list_drivers()
        listed_vehicles = self.service.list_vehicles()

        self.assertEqual(2, len(saved_drivers))
        self.assertEqual(2, len(saved_vehicles))
        self.assertEqual([20, 21], [row["driver_id"] for row in listed_drivers])
        self.assertEqual([220, 221], [row["vehicle_id"] for row in listed_vehicles])

    def test_get_generated_result_missing_batch_raises_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Missing batch"):
            self.service.get_generated_result(999)

    def test_get_generated_result_empty_contract_for_draft_batch(self) -> None:
        batch = self.service.create_dispatch_batch("2026-05-01", created_by="office.user")
        payload = self.service.get_generated_result(int(batch["batch_id"]))

        self.assertEqual({"plans", "order_assignments", "exceptions"}, set(payload.keys()))
        self.assertEqual([], payload["plans"])
        self.assertEqual([], payload["order_assignments"])
        self.assertEqual([], payload["exceptions"])

    def test_get_generated_result_returns_saved_payload(self) -> None:
        batch = self.service.create_dispatch_batch("2026-05-01", created_by="office.user")
        batch_id = int(batch["batch_id"])
        self._seed_minimum_resources()
        self.service.save_batch_orders(batch_id, [self._order(order_id=4101), self._order(order_id=4102, urgency="URGENT")])
        self.service.generate_dispatch_for_batch(batch_id)

        payload = self.service.get_generated_result(batch_id)

        self.assertEqual({"plans", "order_assignments", "exceptions"}, set(payload.keys()))
        self.assertGreaterEqual(len(payload["order_assignments"]), 1)

    def test_save_orders_replaces_existing_and_resets_generated_status(self) -> None:
        batch = self.service.create_dispatch_batch("2026-05-01", created_by="office.user")
        batch_id = int(batch["batch_id"])
        self._seed_minimum_resources()

        self.service.save_batch_orders(batch_id, [self._order(order_id=3001)])
        first_result = self.service.generate_dispatch_for_batch(batch_id)
        self.assertEqual({"plans", "order_assignments", "exceptions"}, set(first_result.keys()))

        self.assertNotEqual(
            {"plans": [], "order_assignments": [], "exceptions": []},
            self.repo.get_generated_results(batch_id),
        )

        self.service.save_batch_orders(batch_id, [self._order(order_id=3002)])
        self.assertEqual("DRAFT", self.service.get_dispatch_batch(batch_id)["status"])
        self.assertEqual(
            {"plans": [], "order_assignments": [], "exceptions": []},
            self.repo.get_generated_results(batch_id),
        )
        loaded_ids = [row["order_id"] for row in self.service.list_batch_orders(batch_id)]
        self.assertEqual([3002], loaded_ids)

    def test_generate_dispatch_returns_contract_and_sets_generated_status(self) -> None:
        batch = self.service.create_dispatch_batch("2026-05-01", created_by="office.user")
        batch_id = int(batch["batch_id"])
        self._seed_minimum_resources()
        self.service.save_batch_orders(batch_id, [self._order(order_id=4001), self._order(order_id=4002, urgency="URGENT")])

        payload = self.service.generate_dispatch_for_batch(batch_id)

        self.assertEqual({"plans", "order_assignments", "exceptions"}, set(payload.keys()))
        self.assertEqual("GENERATED", self.service.get_dispatch_batch(batch_id)["status"])
        self.assertIn("plans", self.repo.get_generated_results(batch_id))

    def test_value_error_for_missing_batch(self) -> None:
        with self.assertRaisesRegex(ValueError, "Missing batch"):
            self.service.get_dispatch_batch(999)
        with self.assertRaisesRegex(ValueError, "Missing batch"):
            self.service.save_batch_orders(999, [self._order(order_id=5001)])
        with self.assertRaisesRegex(ValueError, "Missing batch"):
            self.service.generate_dispatch_for_batch(999)

    def test_value_error_for_no_orders_in_batch(self) -> None:
        batch_no_orders = self.service.create_dispatch_batch("2026-05-01", created_by="office.user")
        with self.assertRaisesRegex(ValueError, "No orders in batch"):
            self.service.generate_dispatch_for_batch(int(batch_no_orders["batch_id"]))

    def test_value_error_for_no_active_drivers(self) -> None:
        batch_no_drivers = self.service.create_dispatch_batch("2026-05-02", created_by="office.user")
        self.repo.seed_vehicle(self._vehicle(vehicle_id=11))
        self.service.save_batch_orders(int(batch_no_drivers["batch_id"]), [self._order(order_id=5002)])
        with self.assertRaisesRegex(ValueError, "No active drivers"):
            self.service.generate_dispatch_for_batch(int(batch_no_drivers["batch_id"]))

    def test_value_error_for_no_active_vehicles(self) -> None:
        batch_no_vehicles = self.service.create_dispatch_batch("2026-05-03", created_by="office.user")
        self.repo.seed_driver(self._driver(driver_id=12))
        self.service.save_batch_orders(int(batch_no_vehicles["batch_id"]), [self._order(order_id=5003)])
        with self.assertRaisesRegex(ValueError, "No active vehicles"):
            self.service.generate_dispatch_for_batch(int(batch_no_vehicles["batch_id"]))

    def test_generate_resolves_order_and_driver_coordinates_and_persists(self) -> None:
        geocoder = StaticAddressGeocoder(
            mapping={
                "Depot": (-37.7800, 144.9300),
                "98-102 Hume Hwy, Somerton VIC 3062, Australia": (-37.6461, 144.9525),
            }
        )
        service = DispatchBatchService(repository=self.repo, address_geocoder=geocoder)
        batch = service.create_dispatch_batch("2026-05-06", created_by="office.user")
        batch_id = int(batch["batch_id"])

        self.repo.seed_driver(self._driver(driver_id=31, with_coordinates=False))
        self.repo.seed_vehicle(self._vehicle(vehicle_id=301, rego="1GEO31"))
        service.save_batch_orders(batch_id, [self._order(order_id=6101, with_coordinates=False)])

        payload = service.generate_dispatch_for_batch(batch_id)

        self.assertEqual({"plans", "order_assignments", "exceptions"}, set(payload.keys()))
        persisted_order = service.list_batch_orders(batch_id)[0]
        self.assertAlmostEqual(-37.6461, float(persisted_order["lat"]), places=4)
        self.assertAlmostEqual(144.9525, float(persisted_order["lng"]), places=4)
        persisted_driver = service.list_drivers()[0]
        self.assertAlmostEqual(-37.7800, float(persisted_driver["start_lat"]), places=4)
        self.assertAlmostEqual(144.9300, float(persisted_driver["start_lng"]), places=4)
        self.assertAlmostEqual(-37.7800, float(persisted_driver["end_lat"]), places=4)
        self.assertAlmostEqual(144.9300, float(persisted_driver["end_lng"]), places=4)

    def test_generate_with_unresolved_address_does_not_crash_and_keeps_contract(self) -> None:
        geocoder = StaticAddressGeocoder(mapping={"Depot": (-37.7800, 144.9300)})
        service = DispatchBatchService(repository=self.repo, address_geocoder=geocoder)
        batch = service.create_dispatch_batch("2026-05-07", created_by="office.user")
        batch_id = int(batch["batch_id"])

        self.repo.seed_driver(self._driver(driver_id=41, with_coordinates=False))
        self.repo.seed_vehicle(self._vehicle(vehicle_id=401, rego="1GEO41"))
        unresolved_order = self._order(order_id=6201, with_coordinates=False)
        unresolved_order["delivery_address"] = "Unknown Address For Geocoder"
        service.save_batch_orders(batch_id, [unresolved_order])

        payload = service.generate_dispatch_for_batch(batch_id)

        self.assertEqual({"plans", "order_assignments", "exceptions"}, set(payload.keys()))
        self.assertGreaterEqual(len(payload["exceptions"]), 1)

    def _seed_minimum_resources(self) -> None:
        self.repo.seed_driver(self._driver(driver_id=1))
        self.repo.seed_driver(self._driver(driver_id=2, preferred_zone_codes=("WEST",)))
        self.repo.seed_vehicle(self._vehicle(vehicle_id=101, rego="1AAA11"))
        self.repo.seed_vehicle(self._vehicle(vehicle_id=102, rego="1BBB22"))

    @staticmethod
    def _order(order_id: int | str, urgency: str = "NORMAL", with_coordinates: bool = True) -> dict[str, object]:
        lat = -37.8136 if with_coordinates else None
        lng = 144.9631 if with_coordinates else None
        address = f"Order-{order_id} Address" if with_coordinates else "98-102 Hume Hwy, Somerton VIC 3062, Australia"
        return {
            "order_id": order_id,
            "dispatch_date": "2026-05-01",
            "delivery_address": address,
            "lat": lat,
            "lng": lng,
            "zone_code": "LOCAL",
            "urgency": urgency,
            "window_start": "08:00",
            "window_end": "12:00",
            "designated_driver_id": None,
            "load_type": "MIXED",
            "kg_count": 10.5,
            "pallet_count": 1,
            "bag_count": 2,
            "postcode": "3000",
            "suburb": "Melbourne",
            "metadata": {},
        }

    @staticmethod
    def _driver(
        driver_id: int,
        preferred_zone_codes: tuple[str, ...] = ("LOCAL",),
        with_coordinates: bool = True,
    ) -> dict[str, object]:
        start_lat = -37.8100 if with_coordinates else None
        start_lng = 144.9600 if with_coordinates else None
        end_lat = -37.8100 if with_coordinates else None
        end_lng = 144.9600 if with_coordinates else None
        return {
            "driver_id": driver_id,
            "shift_start": "07:00",
            "shift_end": "17:00",
            "is_available": True,
            "start_location": "Depot",
            "end_location": "Depot",
            "preferred_zone_codes": list(preferred_zone_codes),
            "historical_vehicle_ids": [],
            "branch_no": None,
            "start_lat": start_lat,
            "start_lng": start_lng,
            "end_lat": end_lat,
            "end_lng": end_lng,
            "metadata": {"name": f"Driver {driver_id}"},
        }

    @staticmethod
    def _vehicle(vehicle_id: int, rego: str = "1XYZ99") -> dict[str, object]:
        return {
            "vehicle_id": vehicle_id,
            "vehicle_type": "van",
            "is_available": True,
            "kg_capacity": 1000.0,
            "pallet_capacity": 6,
            "tub_capacity": 12,
            "trolley_capacity": 4,
            "stillage_capacity": 2,
            "loose_capacity": None,
            "metadata": {"rego": rego},
        }


if __name__ == "__main__":
    unittest.main()
