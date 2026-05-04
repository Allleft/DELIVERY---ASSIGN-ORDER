"""Dispatch batch service for Office Dispatch Workbench MVP (Phase 2A)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from backend.db.repository import DispatchRepository, InMemoryDispatchRepository
from dispatch_optimizer.cli import build_drivers, build_orders, build_vehicles, serialize_result
from dispatch_optimizer.engine import DispatchEngine
from dispatch_optimizer.providers import HaversineTravelTimeProvider


class DispatchBatchService:
    """Service layer for dispatch batch lifecycle and generation."""

    def __init__(
        self,
        repository: DispatchRepository,
        zone_by_postcode: dict[str, str] | None = None,
    ) -> None:
        self.repository = repository
        self.zone_by_postcode = zone_by_postcode or {}
        self.travel_provider = HaversineTravelTimeProvider()

    def create_dispatch_batch(self, dispatch_date: str | date, created_by: str, notes: str | None = None) -> dict[str, Any]:
        return self.repository.create_batch(dispatch_date=dispatch_date, created_by=created_by, notes=notes)

    def list_dispatch_batches(self) -> list[dict[str, Any]]:
        return self.repository.list_batches()

    def get_dispatch_batch(self, batch_id: int) -> dict[str, Any]:
        batch = self.repository.get_batch(batch_id)
        if batch is None:
            raise ValueError(f"Missing batch: {batch_id}")
        return batch

    def save_batch_orders(self, batch_id: int, orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self._require_batch(batch_id)
        self.repository.replace_batch_orders(batch_id, orders)
        self.repository.clear_generated_results(batch_id)
        self.repository.update_batch(batch_id, status="DRAFT", generated_at=None)
        return self.repository.list_batch_orders(batch_id)

    def list_batch_orders(self, batch_id: int) -> list[dict[str, Any]]:
        self._require_batch(batch_id)
        return self.repository.list_batch_orders(batch_id)

    def save_drivers(self, drivers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.repository.replace_drivers(drivers)
        return self.repository.list_drivers()

    def list_drivers(self) -> list[dict[str, Any]]:
        return self.repository.list_drivers()

    def save_vehicles(self, vehicles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.repository.replace_vehicles(vehicles)
        return self.repository.list_vehicles()

    def list_vehicles(self) -> list[dict[str, Any]]:
        return self.repository.list_vehicles()

    def get_generated_result(self, batch_id: int) -> dict[str, Any]:
        self._require_batch(batch_id)
        payload = self.repository.get_generated_results(batch_id)
        if not isinstance(payload, dict):
            payload = {}
        plans = payload.get("plans")
        assignments = payload.get("order_assignments")
        exceptions = payload.get("exceptions")
        return {
            "plans": list(plans) if isinstance(plans, list) else [],
            "order_assignments": list(assignments) if isinstance(assignments, list) else [],
            "exceptions": list(exceptions) if isinstance(exceptions, list) else [],
        }

    def generate_dispatch_for_batch(self, batch_id: int) -> dict[str, Any]:
        batch = self._require_batch(batch_id)
        raw_orders = self.repository.list_batch_orders(batch_id)
        if not raw_orders:
            raise ValueError(f"No orders in batch: {batch_id}")

        raw_drivers = self.repository.list_active_drivers()
        if not raw_drivers:
            raise ValueError("No active drivers")

        raw_vehicles = self.repository.list_active_vehicles()
        if not raw_vehicles:
            raise ValueError("No active vehicles")

        zone_map = self._resolve_zone_map(raw_orders)
        engine = DispatchEngine(
            travel_provider=self.travel_provider,
            zone_by_postcode=zone_map,
        )
        result = engine.plan_dispatch(
            build_orders(raw_orders),
            build_drivers(raw_drivers),
            build_vehicles(raw_vehicles),
        )
        serialized = serialize_result(result)
        self.repository.save_generated_results(batch_id, serialized)
        self.repository.update_batch(
            batch_id,
            status="GENERATED",
            generated_at=datetime.utcnow().isoformat(timespec="seconds"),
            dispatch_date=batch.get("dispatch_date"),
        )
        return serialized

    def _require_batch(self, batch_id: int) -> dict[str, Any]:
        batch = self.repository.get_batch(batch_id)
        if batch is None:
            raise ValueError(f"Missing batch: {batch_id}")
        return batch

    def _resolve_zone_map(self, orders: list[dict[str, Any]]) -> dict[str, str]:
        zone_map = dict(self.zone_by_postcode)
        for order in orders:
            postcode = order.get("postcode")
            zone_code = order.get("zone_code")
            if postcode is None or zone_code is None:
                continue
            postcode_key = str(postcode).strip()
            zone_value = str(zone_code).strip()
            if postcode_key and zone_value:
                zone_map[postcode_key] = zone_value
        return zone_map


_default_repository = InMemoryDispatchRepository()
_default_service = DispatchBatchService(repository=_default_repository)


def create_dispatch_batch(dispatch_date: str | date, created_by: str, notes: str | None = None) -> dict[str, Any]:
    return _default_service.create_dispatch_batch(dispatch_date=dispatch_date, created_by=created_by, notes=notes)


def list_dispatch_batches() -> list[dict[str, Any]]:
    return _default_service.list_dispatch_batches()


def get_dispatch_batch(batch_id: int) -> dict[str, Any]:
    return _default_service.get_dispatch_batch(batch_id)


def save_batch_orders(batch_id: int, orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _default_service.save_batch_orders(batch_id=batch_id, orders=orders)


def list_batch_orders(batch_id: int) -> list[dict[str, Any]]:
    return _default_service.list_batch_orders(batch_id=batch_id)


def save_drivers(drivers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _default_service.save_drivers(drivers=drivers)


def list_drivers() -> list[dict[str, Any]]:
    return _default_service.list_drivers()


def save_vehicles(vehicles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _default_service.save_vehicles(vehicles=vehicles)


def list_vehicles() -> list[dict[str, Any]]:
    return _default_service.list_vehicles()


def get_generated_result(batch_id: int) -> dict[str, Any]:
    return _default_service.get_generated_result(batch_id=batch_id)


def generate_dispatch_for_batch(batch_id: int) -> dict[str, Any]:
    return _default_service.generate_dispatch_for_batch(batch_id=batch_id)


def update_manual_assignment(assignment_id: str, payload: dict[str, Any]) -> Any:
    raise NotImplementedError("Planned for Phase 2B: manual assignment workflow.")


def lock_dispatch_batch(batch_id: str, user_name: str) -> Any:
    raise NotImplementedError("Planned for Phase 2B: lock workflow with audit logging.")
