from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from .engine import DispatchEngine, DispatchEngineResult
from .models import (
    DispatchDriver,
    DispatchOrder,
    DispatchVehicle,
    LoadType,
    Urgency,
    minutes_to_hhmm,
    parse_date,
    to_minutes,
)
from .providers import (
    CachedTravelTimeProvider,
    FallbackTravelTimeProvider,
    GoogleRoutesTravelTimeProvider,
    HaversineTravelTimeProvider,
    StaticGeocoder,
)


LOGGER = logging.getLogger(__name__)


def load_payload(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_orders(raw_orders: list[dict]) -> list[DispatchOrder]:
    return [
        DispatchOrder(
            order_id=record["order_id"],
            dispatch_date=parse_date(record["dispatch_date"]),
            delivery_address=record["delivery_address"],
            lat=record.get("lat"),
            lng=record.get("lng"),
            zone_code=record.get("zone_code"),
            urgency=Urgency(record.get("urgency", "NORMAL")),
            window_start=to_minutes(record["window_start"]),
            window_end=to_minutes(record["window_end"]),
            designated_driver_id=record.get("designated_driver_id"),
            load_type=LoadType(record.get("load_type", "MIXED")),
            kg_count=record.get("kg_count", 0.0),
            pallet_count=record.get("pallet_count", 0),
            bag_count=record.get("bag_count", 0),
            postcode=record.get("postcode"),
            suburb=record.get("suburb"),
            metadata=record.get("metadata", {}),
        )
        for record in raw_orders
    ]


def build_drivers(raw_drivers: list[dict]) -> list[DispatchDriver]:
    return build_drivers_with_legacy(raw_drivers, legacy_zone_code_by_id={})


def build_drivers_with_legacy(
    raw_drivers: list[dict],
    legacy_zone_code_by_id: dict[str, str] | None = None,
) -> list[DispatchDriver]:
    legacy_zone_code_by_id = legacy_zone_code_by_id or {}
    return [
        DispatchDriver(
            driver_id=record["driver_id"],
            shift_start=to_minutes(record["shift_start"]),
            shift_end=to_minutes(record["shift_end"]),
            is_available=record.get("is_available", True),
            start_location=record["start_location"],
            end_location=record["end_location"],
            preferred_zone_codes=_resolve_driver_zone_codes(record, legacy_zone_code_by_id),
            historical_vehicle_ids=tuple(record.get("historical_vehicle_ids", [])),
            branch_no=record.get("branch_no"),
            start_lat=record.get("start_lat"),
            start_lng=record.get("start_lng"),
            end_lat=record.get("end_lat"),
            end_lng=record.get("end_lng"),
            metadata=record.get("metadata", {}),
        )
        for record in raw_drivers
    ]


def _resolve_driver_zone_codes(record: dict, legacy_zone_code_by_id: dict[str, str]) -> tuple[str, ...]:
    preferred_zone_codes = record.get("preferred_zone_codes")
    if preferred_zone_codes is not None:
        return tuple(str(code).strip() for code in preferred_zone_codes if str(code).strip())

    resolved_from_legacy: list[str] = []
    unresolved_zone_ids: list[str] = []
    for zone_id in record.get("preferred_zone_ids", []):
        mapped_code = legacy_zone_code_by_id.get(str(zone_id))
        if mapped_code and str(mapped_code).strip():
            resolved_from_legacy.append(str(mapped_code).strip())
        else:
            unresolved_zone_ids.append(str(zone_id))

    if unresolved_zone_ids:
        metadata = record.setdefault("metadata", {})
        metadata["legacy_zone_ids_unmapped"] = unresolved_zone_ids
    return tuple(resolved_from_legacy)


def build_vehicles(raw_vehicles: list[dict]) -> list[DispatchVehicle]:
    return [
        DispatchVehicle(
            vehicle_id=record["vehicle_id"],
            vehicle_type=record["vehicle_type"],
            is_available=record.get("is_available", True),
            kg_capacity=record.get("kg_capacity", 0.0),
            pallet_capacity=record.get("pallet_capacity", 0),
            tub_capacity=record.get("tub_capacity", 0),
            trolley_capacity=record.get("trolley_capacity", 0),
            stillage_capacity=record.get("stillage_capacity", 0),
            loose_capacity=record.get("loose_capacity"),
            metadata=record.get("metadata", {}),
        )
        for record in raw_vehicles
    ]


def serialize_result(result: DispatchEngineResult) -> dict:
    def _to_hhmm_or_none(value: int | None) -> str | None:
        if value is None:
            return None
        return minutes_to_hhmm(value)

    return {
        "plans": [
            {
                "plan_id": plan.plan_id,
                "dispatch_date": plan.dispatch_date.isoformat(),
                "driver_id": plan.driver_id,
                "vehicle_id": plan.vehicle_id,
                "order_ids": list(plan.order_ids),
                "total_orders": plan.total_orders,
                "load_summary": plan.load_summary,
                "zone_code": plan.zone_code,
                "time_window_start": minutes_to_hhmm(plan.time_window_start),
                "time_window_end": minutes_to_hhmm(plan.time_window_end),
                "urgent_order_count": plan.urgent_order_count,
                "objective_score": plan.objective_score,
                "explanation": list(plan.explanation),
                "planned_start": _to_hhmm_or_none(plan.planned_start),
                "planned_finish": _to_hhmm_or_none(plan.planned_finish),
                "etas": plan.etas if plan.etas else {},
                "stop_sequence": [
                    {
                        "order_id": stop.order_id,
                        "sequence": stop.sequence,
                        "eta": _to_hhmm_or_none(stop.eta),
                        "departure": _to_hhmm_or_none(stop.departure),
                        "travel_from_previous": stop.travel_from_previous,
                    }
                    for stop in plan.stop_sequence
                ],
            }
            for plan in result.plans
        ],
        "order_assignments": [
            {
                "order_id": assignment.order_id,
                "plan_id": assignment.plan_id,
                "dispatch_date": assignment.dispatch_date.isoformat(),
                "driver_id": assignment.driver_id,
                "vehicle_id": assignment.vehicle_id,
                "stop_sequence": assignment.stop_sequence,
                "eta": _to_hhmm_or_none(assignment.eta),
                "departure": _to_hhmm_or_none(assignment.departure),
                "planned_start": _to_hhmm_or_none(assignment.planned_start),
                "planned_finish": _to_hhmm_or_none(assignment.planned_finish),
                "objective_score": assignment.objective_score,
                "postcode": assignment.postcode,
                "zone_code": assignment.zone_code,
                "status": assignment.status,
                "explanation": list(assignment.explanation),
            }
            for assignment in result.order_assignments
        ],
        "exceptions": [
            {
                "scope": exception.scope,
                "entity_id": exception.entity_id,
                "reason_code": exception.reason_code,
                "reason_text": exception.reason_text,
                "suggested_action": exception.suggested_action,
            }
            for exception in result.exceptions
        ],
    }


def build_travel_provider(config: dict, cache_path: str | Path):
    google_config = config.get("google_routes", {})
    if not isinstance(google_config, dict):
        google_config = {}

    def read_value(
        key: str,
        *,
        aliases: tuple[str, ...] = (),
        env_var: str | None = None,
        default=None,
    ):
        if env_var:
            env_value = os.getenv(env_var)
            if env_value not in (None, ""):
                return env_value
        for source in (google_config, config):
            for candidate in (key, *aliases):
                if candidate in source and source[candidate] not in (None, ""):
                    return source[candidate]
        return default

    def as_int(value, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def as_float(value, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    haversine_provider = HaversineTravelTimeProvider()
    api_key = read_value(
        "google_routes_api_key",
        aliases=("api_key",),
        env_var="GOOGLE_ROUTES_API_KEY",
        default="",
    )
    if not str(api_key).strip():
        LOGGER.warning("Google Routes API key is missing. Falling back to Haversine travel time provider.")
        return CachedTravelTimeProvider(haversine_provider, cache_path)

    google_provider = GoogleRoutesTravelTimeProvider(
        api_key=str(api_key),
        base_url=str(
            read_value(
                "google_routes_base_url",
                aliases=("base_url",),
                env_var="GOOGLE_ROUTES_BASE_URL",
                default=GoogleRoutesTravelTimeProvider.DEFAULT_BASE_URL,
            )
        ),
        routing_preference=str(
            read_value(
                "routing_preference",
                env_var="GOOGLE_ROUTES_ROUTING_PREFERENCE",
                default="TRAFFIC_AWARE",
            )
        ),
        departure_time_strategy=str(
            read_value(
                "departure_time_strategy",
                env_var="GOOGLE_ROUTES_DEPARTURE_TIME_STRATEGY",
                default="CURRENT_BUCKET",
            )
        ),
        departure_time_bucket_minutes=as_int(
            read_value(
                "departure_time_bucket_minutes",
                env_var="GOOGLE_ROUTES_DEPARTURE_TIME_BUCKET_MINUTES",
                default=15,
            ),
            15,
        ),
        request_timeout_seconds=as_float(
            read_value(
                "request_timeout_seconds",
                env_var="GOOGLE_ROUTES_TIMEOUT_SECONDS",
                default=8.0,
            ),
            8.0,
        ),
        max_retries=as_int(
            read_value(
                "max_retries",
                env_var="GOOGLE_ROUTES_MAX_RETRIES",
                default=2,
            ),
            2,
        ),
        backoff_seconds=as_float(
            read_value(
                "backoff_seconds",
                env_var="GOOGLE_ROUTES_BACKOFF_SECONDS",
                default=0.5,
            ),
            0.5,
        ),
        prefetch_max_pairs_total=as_int(
            read_value(
                "prefetch_max_pairs_total",
                env_var="GOOGLE_ROUTES_PREFETCH_MAX_PAIRS",
                default=120,
            ),
            120,
        ),
        prefetch_batch_size=as_int(
            read_value(
                "prefetch_batch_size",
                env_var="GOOGLE_ROUTES_PREFETCH_BATCH_SIZE",
                default=25,
            ),
            25,
        ),
    )
    primary_provider = CachedTravelTimeProvider(google_provider, cache_path)
    return FallbackTravelTimeProvider(primary=primary_provider, fallback=haversine_provider)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the dispatch optimizer against a JSON snapshot.")
    parser.add_argument("snapshot", help="Path to the dispatch snapshot JSON file.")
    parser.add_argument(
        "--cache",
        default="cache/travel-matrix.json",
        help="Path to the local travel matrix cache JSON file.",
    )
    args = parser.parse_args()

    payload = load_payload(args.snapshot)
    config = payload.get("config", payload)
    geocoder = StaticGeocoder(config.get("geocoder", {}))
    travel_provider = build_travel_provider(config, args.cache)
    engine = DispatchEngine(
        travel_provider=travel_provider,
        geocoder=geocoder,
        zone_by_postcode=config.get("zone_by_postcode", {}),
        branch_locations=config.get("branch_locations", {}),
    )
    result = engine.plan_dispatch(
        orders=build_orders(payload.get("orders", [])),
        drivers=build_drivers_with_legacy(
            payload.get("drivers", []),
            legacy_zone_code_by_id=config.get("legacy_zone_code_by_id", {}),
        ),
        vehicles=build_vehicles(payload.get("vehicles", [])),
    )
    serializable = serialize_result(result)
    print(json.dumps(serializable, indent=2))


if __name__ == "__main__":
    main()
