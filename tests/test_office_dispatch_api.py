from __future__ import annotations

import unittest

from backend.api.dispatch import (
    create_batch,
    generate_batch_plan,
    get_batch,
    list_batch_orders,
    save_batch_orders,
)
from backend.db.repository import InMemoryDispatchRepository
from backend.services.dispatch_service import DispatchBatchService


class OfficeDispatchApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = InMemoryDispatchRepository()
        self.service = DispatchBatchService(repository=self.repo)

    def test_create_batch_creates_draft(self) -> None:
        batch = create_batch(
            {
                "dispatch_date": "2026-05-02",
                "created_by": "api.user",
                "notes": "api-create",
            },
            service=self.service,
        )

        self.assertEqual("DRAFT", batch["status"])
        self.assertEqual("2026-05-02", batch["dispatch_date"])

    def test_create_batch_missing_dispatch_date_raises_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "dispatch_date"):
            create_batch({"created_by": "api.user"}, service=self.service)

    def test_create_batch_missing_created_by_raises_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "created_by"):
            create_batch({"dispatch_date": "2026-05-02"}, service=self.service)

    def test_save_batch_orders_saves_and_lists_orders(self) -> None:
        batch = create_batch({"dispatch_date": "2026-05-02", "created_by": "api.user"}, service=self.service)
        batch_id = int(batch["batch_id"])
        orders = [self._order(order_id=8001), self._order(order_id="8002A")]

        saved = save_batch_orders(batch_id, orders, service=self.service)
        listed = list_batch_orders(batch_id, service=self.service)

        self.assertEqual(2, len(saved))
        self.assertEqual(2, len(listed))
        self.assertEqual({8001, "8002A"}, {item["order_id"] for item in listed})

    def test_save_batch_orders_with_non_list_payload_raises_value_error(self) -> None:
        batch = create_batch({"dispatch_date": "2026-05-02", "created_by": "api.user"}, service=self.service)
        with self.assertRaisesRegex(ValueError, "must be a list"):
            save_batch_orders(int(batch["batch_id"]), {"order_id": 1}, service=self.service)  # type: ignore[arg-type]

    def test_save_batch_orders_missing_required_order_field_raises_value_error(self) -> None:
        batch = create_batch({"dispatch_date": "2026-05-02", "created_by": "api.user"}, service=self.service)
        invalid_orders = [self._order(order_id=9001)]
        invalid_orders[0].pop("postcode")

        with self.assertRaisesRegex(ValueError, "postcode"):
            save_batch_orders(int(batch["batch_id"]), invalid_orders, service=self.service)

    def test_generate_batch_plan_returns_exact_top_level_contract_keys(self) -> None:
        batch = create_batch({"dispatch_date": "2026-05-02", "created_by": "api.user"}, service=self.service)
        batch_id = int(batch["batch_id"])
        self.repo.seed_driver(self._driver(driver_id=91))
        self.repo.seed_vehicle(self._vehicle(vehicle_id=101))
        save_batch_orders(batch_id, [self._order(order_id=9101), self._order(order_id=9102, urgency="URGENT")], service=self.service)

        result = generate_batch_plan(batch_id, service=self.service)

        self.assertEqual({"plans", "order_assignments", "exceptions"}, set(result.keys()))

    def test_get_batch_missing_id_propagates_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Missing batch"):
            get_batch(999, service=self.service)

    @staticmethod
    def _order(order_id: int | str, urgency: str = "NORMAL") -> dict[str, object]:
        return {
            "order_id": order_id,
            "dispatch_date": "2026-05-02",
            "delivery_address": f"Order-{order_id} Address",
            "lat": -37.8136,
            "lng": 144.9631,
            "zone_code": "LOCAL",
            "urgency": urgency,
            "window_start": "08:00",
            "window_end": "12:00",
            "designated_driver_id": None,
            "load_type": "MIXED",
            "kg_count": 8.5,
            "pallet_count": 1,
            "bag_count": 2,
            "postcode": "3000",
            "suburb": "Melbourne",
            "metadata": {},
        }

    @staticmethod
    def _driver(driver_id: int) -> dict[str, object]:
        return {
            "driver_id": driver_id,
            "shift_start": "07:00",
            "shift_end": "17:00",
            "is_available": True,
            "start_location": "Depot",
            "end_location": "Depot",
            "preferred_zone_codes": ["LOCAL"],
            "historical_vehicle_ids": [],
            "branch_no": None,
            "start_lat": -37.8100,
            "start_lng": 144.9600,
            "end_lat": -37.8100,
            "end_lng": 144.9600,
            "metadata": {"name": f"Driver {driver_id}"},
        }

    @staticmethod
    def _vehicle(vehicle_id: int) -> dict[str, object]:
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
            "metadata": {"rego": f"REGO-{vehicle_id}"},
        }


if __name__ == "__main__":
    unittest.main()

