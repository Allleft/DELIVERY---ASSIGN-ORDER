"""Thin API wrapper functions for Office Dispatch backend service layer."""

from __future__ import annotations

from typing import Any, Protocol

import backend.services.dispatch_service as service_module


_REQUIRED_CREATE_BATCH_FIELDS = ("dispatch_date", "created_by")
_REQUIRED_ORDER_FIELDS = (
    "order_id",
    "dispatch_date",
    "delivery_address",
    "postcode",
    "window_start",
    "window_end",
)
_REQUIRED_DRIVER_FIELDS = (
    "driver_id",
    "shift_start",
    "shift_end",
    "is_available",
)
_REQUIRED_VEHICLE_FIELDS = (
    "vehicle_id",
    "vehicle_type",
    "is_available",
)


class _DispatchBatchServiceProtocol(Protocol):
    def list_dispatch_batches(self) -> list[dict[str, Any]]: ...

    def create_dispatch_batch(self, dispatch_date: str, created_by: str, notes: str | None = None) -> dict[str, Any]: ...

    def get_dispatch_batch(self, batch_id: int) -> dict[str, Any]: ...

    def save_batch_orders(self, batch_id: int, orders: list[dict[str, Any]]) -> list[dict[str, Any]]: ...

    def list_batch_orders(self, batch_id: int) -> list[dict[str, Any]]: ...

    def save_drivers(self, drivers: list[dict[str, Any]]) -> list[dict[str, Any]]: ...

    def list_drivers(self) -> list[dict[str, Any]]: ...

    def save_vehicles(self, vehicles: list[dict[str, Any]]) -> list[dict[str, Any]]: ...

    def list_vehicles(self) -> list[dict[str, Any]]: ...

    def get_generated_result(self, batch_id: int) -> dict[str, Any]: ...

    def generate_dispatch_for_batch(self, batch_id: int) -> dict[str, Any]: ...


def list_batches(service: _DispatchBatchServiceProtocol | None = None) -> list[dict[str, Any]]:
    if service is not None:
        return service.list_dispatch_batches()
    return service_module.list_dispatch_batches()


def create_batch(payload: dict[str, Any], service: _DispatchBatchServiceProtocol | None = None) -> dict[str, Any]:
    payload_obj = _require_dict_payload(payload, "create_batch payload must be a dict.")
    _require_fields(payload_obj, _REQUIRED_CREATE_BATCH_FIELDS, "create_batch payload")
    dispatch_date = str(payload_obj["dispatch_date"])
    created_by = str(payload_obj["created_by"])
    notes = payload_obj.get("notes")

    if service is not None:
        return service.create_dispatch_batch(dispatch_date=dispatch_date, created_by=created_by, notes=notes)
    return service_module.create_dispatch_batch(dispatch_date=dispatch_date, created_by=created_by, notes=notes)


def get_batch(batch_id: int | str, service: _DispatchBatchServiceProtocol | None = None) -> dict[str, Any]:
    normalized_batch_id = _normalize_batch_id(batch_id)
    if service is not None:
        return service.get_dispatch_batch(normalized_batch_id)
    return service_module.get_dispatch_batch(normalized_batch_id)


def save_batch_orders(
    batch_id: int | str,
    payload: list[dict[str, Any]],
    service: _DispatchBatchServiceProtocol | None = None,
) -> list[dict[str, Any]]:
    normalized_batch_id = _normalize_batch_id(batch_id)
    orders = _require_orders_payload(payload)
    if service is not None:
        return service.save_batch_orders(normalized_batch_id, orders)
    return service_module.save_batch_orders(normalized_batch_id, orders)


def list_batch_orders(batch_id: int | str, service: _DispatchBatchServiceProtocol | None = None) -> list[dict[str, Any]]:
    normalized_batch_id = _normalize_batch_id(batch_id)
    if service is not None:
        return service.list_batch_orders(normalized_batch_id)
    return service_module.list_batch_orders(normalized_batch_id)


def save_drivers(payload: list[dict[str, Any]], service: _DispatchBatchServiceProtocol | None = None) -> list[dict[str, Any]]:
    drivers = _require_master_payload(payload, _REQUIRED_DRIVER_FIELDS, "save_drivers payload")
    if service is not None:
        return service.save_drivers(drivers)
    return service_module.save_drivers(drivers)


def list_drivers(service: _DispatchBatchServiceProtocol | None = None) -> list[dict[str, Any]]:
    if service is not None:
        return service.list_drivers()
    return service_module.list_drivers()


def save_vehicles(payload: list[dict[str, Any]], service: _DispatchBatchServiceProtocol | None = None) -> list[dict[str, Any]]:
    vehicles = _require_master_payload(payload, _REQUIRED_VEHICLE_FIELDS, "save_vehicles payload")
    if service is not None:
        return service.save_vehicles(vehicles)
    return service_module.save_vehicles(vehicles)


def list_vehicles(service: _DispatchBatchServiceProtocol | None = None) -> list[dict[str, Any]]:
    if service is not None:
        return service.list_vehicles()
    return service_module.list_vehicles()


def get_batch_result(batch_id: int | str, service: _DispatchBatchServiceProtocol | None = None) -> dict[str, Any]:
    normalized_batch_id = _normalize_batch_id(batch_id)
    if service is not None:
        return service.get_generated_result(normalized_batch_id)
    return service_module.get_generated_result(normalized_batch_id)


def generate_batch_plan(batch_id: int | str, service: _DispatchBatchServiceProtocol | None = None) -> dict[str, Any]:
    normalized_batch_id = _normalize_batch_id(batch_id)
    if service is not None:
        return service.generate_dispatch_for_batch(normalized_batch_id)
    return service_module.generate_dispatch_for_batch(normalized_batch_id)


def lock_batch(batch_id: int | str, service: _DispatchBatchServiceProtocol | None = None) -> Any:
    _ = (batch_id, service)
    raise NotImplementedError("Planned for a later phase: lock batch API.")


def update_manual_assignment(assignment_id: int | str, payload: dict[str, Any], service: _DispatchBatchServiceProtocol | None = None) -> Any:
    _ = (assignment_id, payload, service)
    raise NotImplementedError("Planned for a later phase: manual assignment API.")


def _normalize_batch_id(batch_id: int | str) -> int:
    if isinstance(batch_id, bool):
        raise ValueError("batch_id must be an integer.")
    try:
        return int(batch_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("batch_id must be an integer.") from exc


def _require_dict_payload(payload: Any, message: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(message)
    return payload


def _require_fields(payload: dict[str, Any], required_fields: tuple[str, ...], scope: str) -> None:
    missing = [field for field in required_fields if field not in payload or payload[field] in (None, "")]
    if missing:
        raise ValueError(f"Missing required field(s) in {scope}: {', '.join(missing)}")


def _require_orders_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise ValueError("save_batch_orders payload must be a list.")
    normalized: list[dict[str, Any]] = []
    for index, order in enumerate(payload):
        if not isinstance(order, dict):
            raise ValueError(f"Order at index {index} must be a dict.")
        _require_fields(order, _REQUIRED_ORDER_FIELDS, f"order[{index}]")
        normalized.append(order)
    return normalized


def _require_master_payload(payload: Any, required_fields: tuple[str, ...], scope: str) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise ValueError(f"{scope} must be a list.")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Item at index {index} must be a dict.")
        _require_fields(item, required_fields, f"{scope}[{index}]")
        normalized.append(item)
    return normalized
