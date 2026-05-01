"""Repository abstraction and in-memory implementation for Office Dispatch MVP.

Phase 2A keeps persistence testable without requiring a live MySQL server.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, TypeAlias


Record: TypeAlias = dict[str, object]


class DispatchRepository(Protocol):
    def create_batch(self, dispatch_date: str | date, created_by: str, notes: str | None = None) -> Record: ...

    def list_batches(self) -> list[Record]: ...

    def get_batch(self, batch_id: int) -> Record | None: ...

    def update_batch(self, batch_id: int, **updates: object) -> Record | None: ...

    def replace_batch_orders(self, batch_id: int, orders: list[Record]) -> None: ...

    def list_batch_orders(self, batch_id: int) -> list[Record]: ...

    def list_active_drivers(self) -> list[Record]: ...

    def list_active_vehicles(self) -> list[Record]: ...

    def clear_generated_results(self, batch_id: int) -> None: ...

    def save_generated_results(self, batch_id: int, payload: Record) -> None: ...

    def get_generated_results(self, batch_id: int) -> Record: ...


@dataclass
class InMemoryDispatchRepository:
    """Simple in-memory repository for service-layer tests."""

    _next_batch_id: int = 1

    def __post_init__(self) -> None:
        self._batches: dict[int, Record] = {}
        self._orders_by_batch: dict[int, list[Record]] = {}
        self._generated_by_batch: dict[int, Record] = {}
        self._drivers: list[Record] = []
        self._vehicles: list[Record] = []

    def create_batch(self, dispatch_date: str | date, created_by: str, notes: str | None = None) -> Record:
        batch_id = self._next_batch_id
        self._next_batch_id += 1
        now = datetime.utcnow().isoformat(timespec="seconds")
        batch: Record = {
            "batch_id": batch_id,
            "dispatch_date": _normalize_dispatch_date(dispatch_date),
            "status": "DRAFT",
            "created_by": created_by,
            "notes": notes,
            "created_at": now,
            "updated_at": now,
            "generated_at": None,
            "locked_at": None,
            "locked_by": None,
        }
        self._batches[batch_id] = batch
        self._orders_by_batch[batch_id] = []
        self._generated_by_batch[batch_id] = {"plans": [], "order_assignments": [], "exceptions": []}
        return deepcopy(batch)

    def list_batches(self) -> list[Record]:
        batches = [deepcopy(batch) for batch in self._batches.values()]
        return sorted(batches, key=lambda item: int(item["batch_id"]))

    def get_batch(self, batch_id: int) -> Record | None:
        batch = self._batches.get(batch_id)
        return deepcopy(batch) if batch is not None else None

    def update_batch(self, batch_id: int, **updates: object) -> Record | None:
        batch = self._batches.get(batch_id)
        if batch is None:
            return None
        batch.update(updates)
        batch["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
        return deepcopy(batch)

    def replace_batch_orders(self, batch_id: int, orders: list[Record]) -> None:
        normalized_orders: list[Record] = []
        for order in orders:
            item = deepcopy(order)
            item["batch_id"] = batch_id
            normalized_orders.append(item)
        self._orders_by_batch[batch_id] = normalized_orders

    def list_batch_orders(self, batch_id: int) -> list[Record]:
        return deepcopy(self._orders_by_batch.get(batch_id, []))

    def list_active_drivers(self) -> list[Record]:
        return [deepcopy(driver) for driver in self._drivers if driver.get("is_available", True)]

    def list_active_vehicles(self) -> list[Record]:
        return [deepcopy(vehicle) for vehicle in self._vehicles if vehicle.get("is_available", True)]

    def clear_generated_results(self, batch_id: int) -> None:
        self._generated_by_batch[batch_id] = {"plans": [], "order_assignments": [], "exceptions": []}

    def save_generated_results(self, batch_id: int, payload: Record) -> None:
        self._generated_by_batch[batch_id] = {
            "plans": deepcopy(list(payload.get("plans", []))),
            "order_assignments": deepcopy(list(payload.get("order_assignments", []))),
            "exceptions": deepcopy(list(payload.get("exceptions", []))),
        }

    def get_generated_results(self, batch_id: int) -> Record:
        payload = self._generated_by_batch.get(batch_id)
        if payload is None:
            return {"plans": [], "order_assignments": [], "exceptions": []}
        return deepcopy(payload)

    # Test fixtures helpers
    def seed_driver(self, driver: Record) -> None:
        self._drivers.append(deepcopy(driver))

    def seed_vehicle(self, vehicle: Record) -> None:
        self._vehicles.append(deepcopy(vehicle))


def _normalize_dispatch_date(value: str | date) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)

