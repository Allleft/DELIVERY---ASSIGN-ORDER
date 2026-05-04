from __future__ import annotations

import unittest
from typing import Any

from backend.db.repository import InMemoryDispatchRepository
from backend.services.dispatch_service import DispatchBatchService

_HTTP_IMPORT_ERROR: Exception | None = None

try:
    from fastapi.testclient import TestClient
except Exception as exc:  # pragma: no cover - dependency guard
    TestClient = None  # type: ignore[assignment]
    _HTTP_IMPORT_ERROR = exc
else:
    from backend.main import create_app


class OfficeDispatchHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if _HTTP_IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"HTTP tests require FastAPI/TestClient/httpx: {_HTTP_IMPORT_ERROR}")

    def setUp(self) -> None:
        self.repo = InMemoryDispatchRepository()
        self.service = DispatchBatchService(repository=self.repo)
        self.app = create_app(service=self.service)
        self.client = TestClient(self.app)

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "ok"}, response.json())

    def test_create_batch_creates_draft(self) -> None:
        response = self.client.post(
            "/api/dispatch/batches",
            json={"dispatch_date": "2026-05-03", "created_by": "http.user", "notes": "http-create"},
        )

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("DRAFT", payload["status"])
        self.assertEqual("2026-05-03", payload["dispatch_date"])

    def test_list_batches_returns_created_batch(self) -> None:
        self.client.post("/api/dispatch/batches", json={"dispatch_date": "2026-05-03", "created_by": "http.user"})

        response = self.client.get("/api/dispatch/batches")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(1, len(payload))
        self.assertEqual("DRAFT", payload[0]["status"])

    def test_save_and_list_batch_orders(self) -> None:
        created = self.client.post(
            "/api/dispatch/batches",
            json={"dispatch_date": "2026-05-03", "created_by": "http.user"},
        ).json()
        batch_id = int(created["batch_id"])
        orders = [self._order(order_id=7001), self._order(order_id="7002A")]

        save_response = self.client.post(f"/api/dispatch/batches/{batch_id}/orders", json=orders)
        list_response = self.client.get(f"/api/dispatch/batches/{batch_id}/orders")

        self.assertEqual(200, save_response.status_code)
        self.assertEqual(200, list_response.status_code)
        listed = list_response.json()
        self.assertEqual(2, len(listed))
        self.assertEqual({7001, "7002A"}, {row["order_id"] for row in listed})

    def test_create_batch_missing_dispatch_date_returns_400(self) -> None:
        response = self.client.post("/api/dispatch/batches", json={"created_by": "http.user"})

        self.assertEqual(400, response.status_code)
        self.assertIn("dispatch_date", response.json()["detail"])

    def test_missing_batch_returns_404(self) -> None:
        response = self.client.get("/api/dispatch/batches/999")

        self.assertEqual(404, response.status_code)
        self.assertIn("Missing batch", response.json()["detail"])

    def test_generate_endpoint_returns_contract_keys(self) -> None:
        self.repo.seed_driver(self._driver(driver_id=55))
        self.repo.seed_vehicle(self._vehicle(vehicle_id=66))
        created = self.client.post(
            "/api/dispatch/batches",
            json={"dispatch_date": "2026-05-03", "created_by": "http.user"},
        ).json()
        batch_id = int(created["batch_id"])
        orders = [self._order(order_id=8001), self._order(order_id=8002, urgency="URGENT")]
        self.client.post(f"/api/dispatch/batches/{batch_id}/orders", json=orders)

        response = self.client.post(f"/api/dispatch/batches/{batch_id}/generate")

        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual({"plans", "order_assignments", "exceptions"}, set(payload.keys()))

    def test_save_and_list_drivers(self) -> None:
        payload = [self._driver(driver_id=71), self._driver(driver_id=72)]

        save_response = self.client.post("/api/dispatch/drivers", json=payload)
        list_response = self.client.get("/api/dispatch/drivers")

        self.assertEqual(200, save_response.status_code)
        self.assertEqual(200, list_response.status_code)
        self.assertEqual([71, 72], [item["driver_id"] for item in list_response.json()])

    def test_save_drivers_missing_required_field_returns_400(self) -> None:
        invalid_driver = self._driver(driver_id=73)
        invalid_driver.pop("shift_start")

        response = self.client.post("/api/dispatch/drivers", json=[invalid_driver])

        self.assertEqual(400, response.status_code)
        self.assertIn("shift_start", response.json()["detail"])

    def test_save_and_list_vehicles(self) -> None:
        payload = [self._vehicle(vehicle_id=81), self._vehicle(vehicle_id=82)]

        save_response = self.client.post("/api/dispatch/vehicles", json=payload)
        list_response = self.client.get("/api/dispatch/vehicles")

        self.assertEqual(200, save_response.status_code)
        self.assertEqual(200, list_response.status_code)
        self.assertEqual([81, 82], [item["vehicle_id"] for item in list_response.json()])

    def test_save_vehicles_missing_required_field_returns_400(self) -> None:
        invalid_vehicle = self._vehicle(vehicle_id=83)
        invalid_vehicle.pop("vehicle_type")

        response = self.client.post("/api/dispatch/vehicles", json=[invalid_vehicle])

        self.assertEqual(400, response.status_code)
        self.assertIn("vehicle_type", response.json()["detail"])

    @staticmethod
    def _order(order_id: int | str, urgency: str = "NORMAL") -> dict[str, Any]:
        return {
            "order_id": order_id,
            "dispatch_date": "2026-05-03",
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
    def _driver(driver_id: int) -> dict[str, Any]:
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
    def _vehicle(vehicle_id: int) -> dict[str, Any]:
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
