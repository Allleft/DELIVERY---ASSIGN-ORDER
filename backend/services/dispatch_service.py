"""Dispatch batch service for Office Dispatch Workbench MVP (Phase 2A)."""

from __future__ import annotations

from datetime import UTC, date, datetime
import re
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

    def update_manual_assignment(
        self,
        batch_id: int,
        order_id: int | str,
        driver_id: int | str,
        vehicle_id: int | str,
        manual_reason: str | None = None,
    ) -> dict[str, Any]:
        batch = self._require_batch(batch_id)
        if str(batch.get("status", "")).strip().upper() == "LOCKED":
            raise ValueError(f"Batch is locked: {batch_id}")

        raw_orders = self.repository.list_batch_orders(batch_id)
        target_order = self._find_batch_order(raw_orders, order_id)
        if target_order is None:
            raise ValueError(f"Missing order in batch: {order_id}")

        if not self._entity_exists(self.repository.list_drivers(), "driver_id", driver_id):
            raise ValueError(f"Missing driver: {driver_id}")
        if not self._entity_exists(self.repository.list_vehicles(), "vehicle_id", vehicle_id):
            raise ValueError(f"Missing vehicle: {vehicle_id}")

        payload = self.get_generated_result(batch_id)
        plans = [dict(plan) for plan in payload["plans"]]
        assignments = [dict(assignment) for assignment in payload["order_assignments"]]
        exceptions = [dict(exception) for exception in payload["exceptions"]]

        order_key = self._order_key(target_order.get("order_id", order_id))
        normalized_reason = self._normalize_manual_reason(manual_reason)
        dispatch_date = str(target_order.get("dispatch_date") or batch.get("dispatch_date") or "")

        existing_assignment_index = self._find_assignment_index(assignments, order_key)
        previous_plan_id: str | None = None
        if existing_assignment_index is not None:
            previous_plan_id = self._as_plan_id(assignments[existing_assignment_index].get("plan_id"))

        target_plan_id = self._find_plan_for_group(plans, dispatch_date, driver_id, vehicle_id)
        if target_plan_id is None:
            target_plan_id = self._next_sequential_plan_id(plans)

        manual_assignment = self._build_manual_assignment(
            existing_assignment=assignments[existing_assignment_index] if existing_assignment_index is not None else None,
            target_order=target_order,
            dispatch_date=dispatch_date,
            target_plan_id=target_plan_id,
            driver_id=driver_id,
            vehicle_id=vehicle_id,
            manual_reason=normalized_reason,
        )

        if existing_assignment_index is None:
            assignments.append(manual_assignment)
        else:
            assignments[existing_assignment_index] = manual_assignment

        affected_plan_ids: set[str] = {target_plan_id}
        if previous_plan_id:
            affected_plan_ids.add(previous_plan_id)
        plans = self._rebuild_affected_plans(
            plans=plans,
            assignments=assignments,
            orders=raw_orders,
            affected_plan_ids=affected_plan_ids,
            fallback_dispatch_date=dispatch_date,
        )
        exceptions = self._suppress_unresolved_order_exceptions(exceptions, order_key)

        updated_payload: dict[str, Any] = {
            "plans": plans,
            "order_assignments": assignments,
            "exceptions": exceptions,
        }
        self.repository.save_generated_results(batch_id, updated_payload)
        self.repository.update_batch(batch_id, status="ADJUSTED")
        return self.get_generated_result(batch_id)

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

    @staticmethod
    def _entity_exists(records: list[dict[str, Any]], key: str, expected: int | str) -> bool:
        expected_key = str(expected).strip()
        for record in records:
            if str(record.get(key, "")).strip() == expected_key:
                return True
        return False

    @staticmethod
    def _order_key(order_id: Any) -> str:
        return str(order_id).strip()

    def _find_batch_order(self, orders: list[dict[str, Any]], order_id: int | str) -> dict[str, Any] | None:
        expected_key = self._order_key(order_id)
        for order in orders:
            if self._order_key(order.get("order_id")) == expected_key:
                return dict(order)
        return None

    def _find_assignment_index(self, assignments: list[dict[str, Any]], order_key: str) -> int | None:
        for index, assignment in enumerate(assignments):
            if self._order_key(assignment.get("order_id")) == order_key:
                return index
        return None

    @staticmethod
    def _normalize_manual_reason(manual_reason: str | None) -> str | None:
        if manual_reason is None:
            return None
        normalized = str(manual_reason).strip()
        if normalized == "":
            return None
        return normalized

    @staticmethod
    def _as_plan_id(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None

    def _find_plan_for_group(
        self,
        plans: list[dict[str, Any]],
        dispatch_date: str,
        driver_id: int | str,
        vehicle_id: int | str,
    ) -> str | None:
        target_driver = str(driver_id).strip()
        target_vehicle = str(vehicle_id).strip()
        for plan in plans:
            if str(plan.get("dispatch_date", "")).strip() != dispatch_date:
                continue
            if str(plan.get("driver_id", "")).strip() != target_driver:
                continue
            if str(plan.get("vehicle_id", "")).strip() != target_vehicle:
                continue
            plan_id = self._as_plan_id(plan.get("plan_id"))
            if plan_id is not None:
                return plan_id
        return None

    @staticmethod
    def _next_sequential_plan_id(plans: list[dict[str, Any]]) -> str:
        max_seq = 0
        for plan in plans:
            plan_id = str(plan.get("plan_id", "")).strip()
            match = re.fullmatch(r"PLAN-(\d+)", plan_id)
            if match is None:
                continue
            seq = int(match.group(1))
            if seq > max_seq:
                max_seq = seq
        return f"PLAN-{max_seq + 1:04d}"

    def _build_manual_assignment(
        self,
        *,
        existing_assignment: dict[str, Any] | None,
        target_order: dict[str, Any],
        dispatch_date: str,
        target_plan_id: str,
        driver_id: int | str,
        vehicle_id: int | str,
        manual_reason: str | None,
    ) -> dict[str, Any]:
        base = dict(existing_assignment) if existing_assignment is not None else {}
        order_id = target_order.get("order_id")
        postcode = base.get("postcode")
        if postcode in (None, ""):
            postcode = target_order.get("postcode")
        zone_code = base.get("zone_code")
        if zone_code in (None, ""):
            zone_code = target_order.get("zone_code")
        explanation = base.get("explanation")
        explanation_items: list[str] = list(explanation) if isinstance(explanation, list) else []
        explanation_items.append("Manually assigned by office dispatch.")

        assignment = dict(base)
        assignment["order_id"] = order_id
        assignment["plan_id"] = target_plan_id
        assignment["dispatch_date"] = dispatch_date
        assignment["driver_id"] = driver_id
        assignment["vehicle_id"] = vehicle_id
        assignment["status"] = "MANUALLY_ASSIGNED"
        assignment["assignment_source"] = "MANUAL"
        assignment["manual_reason"] = manual_reason
        assignment["postcode"] = postcode
        assignment["zone_code"] = zone_code
        assignment["stop_sequence"] = assignment.get("stop_sequence")
        assignment["eta"] = assignment.get("eta")
        assignment["departure"] = assignment.get("departure")
        assignment["planned_start"] = assignment.get("planned_start")
        assignment["planned_finish"] = assignment.get("planned_finish")
        assignment["objective_score"] = assignment.get("objective_score", 0)
        assignment["explanation"] = list(dict.fromkeys(explanation_items))
        return assignment

    def _rebuild_affected_plans(
        self,
        *,
        plans: list[dict[str, Any]],
        assignments: list[dict[str, Any]],
        orders: list[dict[str, Any]],
        affected_plan_ids: set[str],
        fallback_dispatch_date: str,
    ) -> list[dict[str, Any]]:
        if not affected_plan_ids:
            return plans

        order_map = {self._order_key(order.get("order_id")): dict(order) for order in orders}
        existing_by_id: dict[str, dict[str, Any]] = {}
        for plan in plans:
            plan_id = self._as_plan_id(plan.get("plan_id"))
            if plan_id is None:
                continue
            existing_by_id[plan_id] = dict(plan)

        assignments_by_plan: dict[str, list[dict[str, Any]]] = {}
        for assignment in assignments:
            plan_id = self._as_plan_id(assignment.get("plan_id"))
            if plan_id is None:
                continue
            if plan_id not in affected_plan_ids:
                continue
            assignments_by_plan.setdefault(plan_id, []).append(assignment)

        for plan_id in affected_plan_ids:
            grouped = assignments_by_plan.get(plan_id, [])
            if not grouped:
                existing_by_id.pop(plan_id, None)
                continue
            existing_by_id[plan_id] = self._build_rebuilt_plan(
                plan_id=plan_id,
                grouped_assignments=grouped,
                order_map=order_map,
                existing_plan=existing_by_id.get(plan_id),
                fallback_dispatch_date=fallback_dispatch_date,
            )

        rebuilt = list(existing_by_id.values())
        rebuilt.sort(key=lambda item: (self._plan_sequence_sort_key(item.get("plan_id")), str(item.get("plan_id", ""))))
        return rebuilt

    def _build_rebuilt_plan(
        self,
        *,
        plan_id: str,
        grouped_assignments: list[dict[str, Any]],
        order_map: dict[str, dict[str, Any]],
        existing_plan: dict[str, Any] | None,
        fallback_dispatch_date: str,
    ) -> dict[str, Any]:
        ordered_assignments = list(grouped_assignments)
        first = ordered_assignments[0]
        dispatch_date = str(first.get("dispatch_date") or fallback_dispatch_date)
        driver_id = first.get("driver_id")
        vehicle_id = first.get("vehicle_id")
        order_ids = [assignment.get("order_id") for assignment in ordered_assignments]
        related_orders = [order_map[self._order_key(order_id)] for order_id in order_ids if self._order_key(order_id) in order_map]

        zone_values = []
        for assignment in ordered_assignments:
            zone = assignment.get("zone_code")
            if zone not in (None, ""):
                zone_values.append(str(zone))
        if not zone_values:
            for order in related_orders:
                zone = order.get("zone_code")
                if zone not in (None, ""):
                    zone_values.append(str(zone))
        unique_zones = list(dict.fromkeys(zone_values))
        if len(unique_zones) == 0:
            zone_code = existing_plan.get("zone_code") if isinstance(existing_plan, dict) else None
        elif len(unique_zones) == 1:
            zone_code = unique_zones[0]
        else:
            zone_code = "MULTI_ZONE"

        urgency_count = 0
        for order in related_orders:
            if str(order.get("urgency", "")).upper() == "URGENT":
                urgency_count += 1

        objective_score = 0
        for assignment in ordered_assignments:
            score = assignment.get("objective_score")
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                objective_score += score

        windows = []
        for order in related_orders:
            start = self._parse_hhmm(order.get("window_start"))
            end = self._parse_hhmm(order.get("window_end"))
            if start is None or end is None:
                continue
            windows.append((start, end))
        if windows:
            time_window_start = self._minutes_to_hhmm(min(start for start, _ in windows))
            time_window_end = self._minutes_to_hhmm(max(end for _, end in windows))
        else:
            time_window_start = existing_plan.get("time_window_start") if isinstance(existing_plan, dict) else None
            time_window_end = existing_plan.get("time_window_end") if isinstance(existing_plan, dict) else None

        load_summary = self._derive_load_summary_from_orders(related_orders)
        if not load_summary and isinstance(existing_plan, dict):
            fallback_load = existing_plan.get("load_summary")
            load_summary = dict(fallback_load) if isinstance(fallback_load, dict) else {}

        explanation_items: list[str] = []
        if isinstance(existing_plan, dict):
            existing_explanation = existing_plan.get("explanation")
            if isinstance(existing_explanation, list):
                explanation_items.extend(str(item) for item in existing_explanation)
        explanation_items.append("Plan updated after manual assignment adjustment.")

        rebuilt = dict(existing_plan) if isinstance(existing_plan, dict) else {}
        rebuilt["plan_id"] = plan_id
        rebuilt["dispatch_date"] = dispatch_date
        rebuilt["driver_id"] = driver_id
        rebuilt["vehicle_id"] = vehicle_id
        rebuilt["order_ids"] = order_ids
        rebuilt["total_orders"] = len(order_ids)
        rebuilt["load_summary"] = load_summary
        rebuilt["zone_code"] = zone_code
        rebuilt["time_window_start"] = time_window_start
        rebuilt["time_window_end"] = time_window_end
        rebuilt["urgent_order_count"] = urgency_count
        rebuilt["objective_score"] = objective_score
        rebuilt["explanation"] = list(dict.fromkeys(explanation_items))
        if "planned_start" not in rebuilt:
            rebuilt["planned_start"] = None
        if "planned_finish" not in rebuilt:
            rebuilt["planned_finish"] = None
        if "etas" not in rebuilt or not isinstance(rebuilt.get("etas"), dict):
            rebuilt["etas"] = {}
        if "stop_sequence" not in rebuilt or not isinstance(rebuilt.get("stop_sequence"), list):
            rebuilt["stop_sequence"] = []
        return rebuilt

    @staticmethod
    def _derive_load_summary_from_orders(orders: list[dict[str, Any]]) -> dict[str, Any]:
        if not orders:
            return {}
        kg = 0.0
        pallets = 0
        loose_units = 0
        for order in orders:
            kg_count = order.get("kg_count")
            pallet_count = order.get("pallet_count")
            bag_count = order.get("bag_count")
            if isinstance(kg_count, (int, float)) and not isinstance(kg_count, bool):
                kg += float(kg_count)
            if isinstance(pallet_count, (int, float)) and not isinstance(pallet_count, bool):
                pallets += int(pallet_count)
            if isinstance(bag_count, (int, float)) and not isinstance(bag_count, bool):
                loose_units += int(bag_count)
        return {
            "kg": kg,
            "pallets": pallets,
            "tubs": 0,
            "loose_units": loose_units,
            "trolleys": 0,
            "stillages": 0,
        }

    def _suppress_unresolved_order_exceptions(
        self,
        exceptions: list[dict[str, Any]],
        target_order_key: str,
    ) -> list[dict[str, Any]]:
        filtered: list[dict[str, Any]] = []
        for exception in exceptions:
            reason_code = str(exception.get("reason_code", "")).upper()
            if not ("UNASSIGNED" in reason_code or "NO_FEASIBLE" in reason_code or "NO_ASSIGNMENT" in reason_code):
                filtered.append(exception)
                continue
            if not self._exception_mentions_order(exception.get("entity_id"), target_order_key):
                filtered.append(exception)
        return filtered

    def _exception_mentions_order(self, entity_id: Any, target_order_key: str) -> bool:
        raw = str(entity_id or "").strip()
        if raw == "":
            return False
        if self._order_key(raw) == target_order_key:
            return True
        if raw.startswith("orders:"):
            members = [self._order_key(item) for item in raw[len("orders:") :].split(",")]
            return target_order_key in members
        return False

    @staticmethod
    def _parse_hhmm(value: Any) -> int | None:
        text = str(value or "").strip()
        if text == "" or ":" not in text:
            return None
        parts = text.split(":")
        if len(parts) != 2:
            return None
        try:
            hour = int(parts[0])
            minute = int(parts[1])
        except ValueError:
            return None
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return None
        return hour * 60 + minute

    @staticmethod
    def _minutes_to_hhmm(value: int) -> str:
        hour = value // 60
        minute = value % 60
        return f"{hour:02d}:{minute:02d}"

    @staticmethod
    def _plan_sequence_sort_key(plan_id: Any) -> tuple[int, int]:
        text = str(plan_id or "").strip()
        match = re.fullmatch(r"PLAN-(\d+)", text)
        if match is None:
            return (1, 0)
        return (0, int(match.group(1)))

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


def update_manual_assignment(
    batch_id: int,
    order_id: int | str,
    driver_id: int | str,
    vehicle_id: int | str,
    manual_reason: str | None = None,
) -> dict[str, Any]:
    return _default_service.update_manual_assignment(
        batch_id=batch_id,
        order_id=order_id,
        driver_id=driver_id,
        vehicle_id=vehicle_id,
        manual_reason=manual_reason,
    )


def lock_dispatch_batch(batch_id: str, user_name: str) -> Any:
    raise NotImplementedError("Planned for Phase 2B: lock workflow with audit logging.")
