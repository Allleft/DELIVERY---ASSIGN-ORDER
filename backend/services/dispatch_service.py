"""Dispatch batch service for Office Dispatch Workbench MVP (Phase 2A)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from backend.db.repository import DispatchRepository, InMemoryDispatchRepository
from backend.services.geocoding import AddressGeocoder
from dispatch_optimizer.cli import build_drivers, build_orders, build_vehicles, serialize_result
from dispatch_optimizer.engine import DispatchEngine
from dispatch_optimizer.providers import HaversineTravelTimeProvider


class DispatchBatchService:
    """Service layer for dispatch batch lifecycle and generation."""

    def __init__(
        self,
        repository: DispatchRepository,
        zone_by_postcode: dict[str, str] | None = None,
        address_geocoder: AddressGeocoder | None = None,
    ) -> None:
        self.repository = repository
        self.zone_by_postcode = zone_by_postcode or {}
        self.address_geocoder = address_geocoder
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

        normalized_orders = self._normalize_orders_with_geocoding(raw_orders)
        normalized_drivers = self._normalize_drivers_with_geocoding(raw_drivers)
        self.repository.replace_batch_orders(batch_id, normalized_orders)
        self.repository.replace_drivers(normalized_drivers)

        zone_map = self._resolve_zone_map(normalized_orders)
        engine = DispatchEngine(
            travel_provider=self.travel_provider,
            zone_by_postcode=zone_map,
        )
        result = engine.plan_dispatch(
            build_orders(normalized_orders),
            build_drivers(normalized_drivers),
            build_vehicles(raw_vehicles),
        )
        serialized = serialize_result(result)
        self.repository.save_generated_results(batch_id, serialized)
        self.repository.update_batch(
            batch_id,
            status="GENERATED",
            generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
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

    def _normalize_orders_with_geocoding(self, orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized_orders: list[dict[str, Any]] = []
        for order in orders:
            item = dict(order)
            if self._has_valid_coordinates(item.get("lat"), item.get("lng")):
                normalized_orders.append(item)
                continue
            for candidate in self._build_order_address_candidates(item):
                point = self._geocode_address(candidate)
                if point is None:
                    continue
                item["lat"] = point["lat"]
                item["lng"] = point["lng"]
                break
            normalized_orders.append(item)
        return normalized_orders

    def _normalize_drivers_with_geocoding(self, drivers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized_drivers: list[dict[str, Any]] = []
        for driver in drivers:
            item = dict(driver)
            if not self._has_valid_coordinates(item.get("start_lat"), item.get("start_lng")):
                point = self._geocode_address(item.get("start_location"))
                if point is not None:
                    item["start_lat"] = point["lat"]
                    item["start_lng"] = point["lng"]
            if not self._has_valid_coordinates(item.get("end_lat"), item.get("end_lng")):
                point = self._geocode_address(item.get("end_location"))
                if point is not None:
                    item["end_lat"] = point["lat"]
                    item["end_lng"] = point["lng"]
            normalized_drivers.append(item)
        return normalized_drivers

    def _build_order_address_candidates(self, order: dict[str, Any]) -> tuple[str, ...]:
        delivery_address = str(order.get("delivery_address") or "").strip()
        suburb = str(order.get("suburb") or "").strip()
        postcode = str(order.get("postcode") or "").strip()
        candidates: list[str] = []
        if delivery_address:
            candidates.append(delivery_address)
            if suburb and postcode:
                candidates.append(f"{delivery_address}, {suburb} {postcode}, Australia")
            if postcode:
                candidates.append(f"{delivery_address}, {postcode}, Australia")
        return tuple(candidates)

    def _geocode_address(self, address: Any) -> dict[str, float] | None:
        if self.address_geocoder is None:
            return None
        raw = str(address or "").strip()
        if raw == "":
            return None
        point = self.address_geocoder.geocode(raw)
        if not isinstance(point, dict):
            return None
        lat = point.get("lat")
        lng = point.get("lng")
        if self._has_valid_coordinates(lat, lng):
            return {"lat": float(lat), "lng": float(lng)}
        return None

    @staticmethod
    def _has_valid_coordinates(lat: Any, lng: Any) -> bool:
        return isinstance(lat, (int, float)) and not isinstance(lat, bool) and isinstance(lng, (int, float)) and not isinstance(lng, bool)


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
