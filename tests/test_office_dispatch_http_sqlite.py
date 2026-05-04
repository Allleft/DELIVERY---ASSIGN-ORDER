from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from backend.db.sqlite_repository import SQLiteDispatchRepository

_HTTP_IMPORT_ERROR: Exception | None = None

try:
    from fastapi.testclient import TestClient
except Exception as exc:  # pragma: no cover - dependency guard
    TestClient = None  # type: ignore[assignment]
    _HTTP_IMPORT_ERROR = exc
else:
    from backend.main import create_app


class OfficeDispatchHttpSqliteRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if _HTTP_IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"HTTP tests require FastAPI/TestClient/httpx: {_HTTP_IMPORT_ERROR}")

    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._temp_dir.name) / "runtime.sqlite3"
        self.geocoder_path = Path(self._temp_dir.name) / "static-geocoder.json"
        self.geocoder_path.write_text(
            json.dumps(
                {
                    "Depot": [-37.7800, 144.9300],
                    "98-102 Hume Hwy, Somerton VIC 3062, Australia": [-37.6461, 144.9525],
                }
            ),
            encoding="utf-8",
        )
        self._env_patch = mock.patch.dict(
            os.environ,
            {
                "OFFICE_DISPATCH_DB_PATH": str(self.db_path),
                "OFFICE_DISPATCH_STATIC_GEOCODER_PATH": str(self.geocoder_path),
            },
            clear=False,
        )
        self._env_patch.start()

        seed_repo = SQLiteDispatchRepository(self.db_path)
        seed_repo.seed_driver(self._driver(driver_id=101, with_coordinates=False))
        seed_repo.seed_vehicle(self._vehicle(vehicle_id=901))
        seed_repo.close()

    def tearDown(self) -> None:
        self._env_patch.stop()
        self._temp_dir.cleanup()

    def test_http_runtime_uses_sqlite_when_env_path_is_set(self) -> None:
        with TestClient(create_app(service=None)) as client:
            created = client.post(
                "/api/dispatch/batches",
                json={"dispatch_date": "2026-05-11", "created_by": "sqlite.http"},
            )
            self.assertEqual(200, created.status_code)
            batch_id = int(created.json()["batch_id"])

            save_orders = client.post(
                f"/api/dispatch/batches/{batch_id}/orders",
                json=[self._order(order_id=7001, with_coordinates=False), self._order(order_id=7002, urgency="URGENT", with_coordinates=False)],
            )
            self.assertEqual(200, save_orders.status_code)

            generated = client.post(f"/api/dispatch/batches/{batch_id}/generate")
            self.assertEqual(200, generated.status_code)
            payload = generated.json()
            self.assertEqual({"plans", "order_assignments", "exceptions"}, set(payload.keys()))

        with TestClient(create_app(service=None)) as client_reopened:
            batches = client_reopened.get("/api/dispatch/batches")
            self.assertEqual(200, batches.status_code)
            self.assertEqual(1, len(batches.json()))
            batch_id = int(batches.json()[0]["batch_id"])

            orders = client_reopened.get(f"/api/dispatch/batches/{batch_id}/orders")
            self.assertEqual(200, orders.status_code)
            self.assertEqual(2, len(orders.json()))

        reopened_repo = SQLiteDispatchRepository(self.db_path)
        try:
            stored_result = reopened_repo.get_generated_results(batch_id)
        finally:
            reopened_repo.close()
        self.assertEqual({"plans", "order_assignments", "exceptions"}, set(stored_result.keys()))
        self.assertGreaterEqual(len(stored_result["order_assignments"]), 1)

    @staticmethod
    def _order(order_id: int | str, urgency: str = "NORMAL", with_coordinates: bool = True) -> dict[str, Any]:
        lat = -37.8136 if with_coordinates else None
        lng = 144.9631 if with_coordinates else None
        address = f"Order-{order_id} Address" if with_coordinates else "98-102 Hume Hwy, Somerton VIC 3062, Australia"
        return {
            "order_id": order_id,
            "dispatch_date": "2026-05-11",
            "delivery_address": address,
            "lat": lat,
            "lng": lng,
            "zone_code": "LOCAL",
            "urgency": urgency,
            "window_start": "08:00",
            "window_end": "12:00",
            "designated_driver_id": None,
            "load_type": "MIXED",
            "kg_count": 9.5,
            "pallet_count": 1,
            "bag_count": 1,
            "postcode": "3000",
            "suburb": "Melbourne",
            "metadata": {},
        }

    @staticmethod
    def _driver(driver_id: int, with_coordinates: bool = True) -> dict[str, Any]:
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
    def _vehicle(vehicle_id: int) -> dict[str, Any]:
        return {
            "vehicle_id": vehicle_id,
            "vehicle_type": "van",
            "is_available": True,
            "kg_capacity": 1200.0,
            "pallet_capacity": 8,
            "tub_capacity": 16,
            "trolley_capacity": 4,
            "stillage_capacity": 2,
            "loose_capacity": None,
            "metadata": {"rego": f"REGO-{vehicle_id}"},
        }


if __name__ == "__main__":
    unittest.main()
