from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum
from typing import Any

FIXED_STOP_MINUTES = 10


class Urgency(str, Enum):
    URGENT = "URGENT"
    NORMAL = "NORMAL"


class LoadType(str, Enum):
    MIXED = "MIXED"
    ON_PALLET = "ON_PALLET"
    LOOSE = "LOOSE"


def to_minutes(value: int | str | time) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, time):
        return value.hour * 60 + value.minute
    if isinstance(value, str):
        parsed = datetime.strptime(value, "%H:%M")
        return parsed.hour * 60 + parsed.minute
    raise TypeError(f"Unsupported time value: {value!r}")


def minutes_to_hhmm(value: int) -> str:
    hours, minutes = divmod(int(value), 60)
    return f"{hours:02d}:{minutes:02d}"


def parse_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


@dataclass(frozen=True)
class LocationRef:
    address: str
    lat: float
    lng: float


@dataclass(frozen=True)
class LoadVector:
    kg: float = 0.0
    pallets: int = 0
    tubs: int = 0
    loose_units: int = 0
    trolleys: int = 0
    stillages: int = 0

    def __add__(self, other: "LoadVector") -> "LoadVector":
        return LoadVector(
            kg=self.kg + other.kg,
            pallets=self.pallets + other.pallets,
            tubs=self.tubs + other.tubs,
            loose_units=self.loose_units + other.loose_units,
            trolleys=self.trolleys + other.trolleys,
            stillages=self.stillages + other.stillages,
        )

    def fits_in(self, capacity: "LoadVector") -> bool:
        return (
            (capacity.kg <= 0 or self.kg <= capacity.kg)
            and self.pallets <= capacity.pallets
            and self.tubs <= capacity.tubs
            and self.loose_units <= capacity.loose_units
            and self.trolleys <= capacity.trolleys
            and self.stillages <= capacity.stillages
        )

    def waste_against(self, capacity: "LoadVector") -> float:
        return (
            (max(capacity.kg - self.kg, 0.0) if capacity.kg > 0 else 0.0)
            + max(capacity.pallets - self.pallets, 0)
            + max(capacity.tubs - self.tubs, 0)
            + max(capacity.loose_units - self.loose_units, 0)
            + max(capacity.trolleys - self.trolleys, 0)
            + max(capacity.stillages - self.stillages, 0)
        )

    def as_dict(self) -> dict[str, float | int]:
        return {
            "kg": round(self.kg, 2),
            "pallets": self.pallets,
            "tubs": self.tubs,
            "loose_units": self.loose_units,
            "trolleys": self.trolleys,
            "stillages": self.stillages,
        }


@dataclass(frozen=True)
class DispatchOrder:
    order_id: int
    dispatch_date: date
    delivery_address: str
    lat: float | None
    lng: float | None
    zone_code: str | None
    urgency: Urgency
    window_start: int
    window_end: int
    designated_driver_id: int | None = None
    load_type: LoadType = LoadType.MIXED
    kg_count: float = 0.0
    pallet_count: int = 0
    bag_count: int = 0
    postcode: str | None = None
    suburb: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def location(self) -> LocationRef | None:
        if self.lat is None or self.lng is None:
            return None
        return LocationRef(self.delivery_address, self.lat, self.lng)


@dataclass(frozen=True)
class DispatchDriver:
    driver_id: int
    shift_start: int
    shift_end: int
    is_available: bool
    start_location: str
    end_location: str
    preferred_zone_codes: tuple[str, ...] = ()
    historical_vehicle_ids: tuple[int, ...] = ()
    branch_no: str | None = None
    start_lat: float | None = None
    start_lng: float | None = None
    end_lat: float | None = None
    end_lng: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def start_ref(self) -> LocationRef | None:
        if self.start_lat is None or self.start_lng is None:
            return None
        return LocationRef(self.start_location, self.start_lat, self.start_lng)

    @property
    def end_ref(self) -> LocationRef | None:
        if self.end_lat is None or self.end_lng is None:
            return None
        return LocationRef(self.end_location, self.end_lat, self.end_lng)


@dataclass(frozen=True)
class DispatchVehicle:
    vehicle_id: int
    vehicle_type: str
    is_available: bool
    kg_capacity: float = 0.0
    pallet_capacity: int = 0
    tub_capacity: int = 0
    trolley_capacity: int = 0
    stillage_capacity: int = 0
    loose_capacity: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def capacity(self) -> LoadVector:
        loose_capacity = self.loose_capacity
        if loose_capacity is None:
            loose_capacity = self.tub_capacity * 4
        return LoadVector(
            kg=self.kg_capacity,
            pallets=self.pallet_capacity,
            tubs=self.tub_capacity,
            loose_units=loose_capacity,
            trolleys=self.trolley_capacity,
            stillages=self.stillage_capacity,
        )


@dataclass
class DispatchRun:
    run_id: str
    dispatch_date: date
    zone_code: str
    bucket_start: int
    bucket_end: int
    orders: list[DispatchOrder]
    load: LoadVector
    estimated_service_minutes: int
    designated_driver_id: int | None = None
    origin_run_id: str | None = None
    repair_round: int = 0

    @property
    def window_start(self) -> int:
        return min(order.window_start for order in self.orders)

    @property
    def window_end(self) -> int:
        return max(order.window_end for order in self.orders)

    @property
    def centroid(self) -> tuple[float, float] | None:
        points = [(order.lat, order.lng) for order in self.orders if order.lat is not None and order.lng is not None]
        if not points:
            return None
        lat = sum(point[0] for point in points) / len(points)
        lng = sum(point[1] for point in points) / len(points)
        return lat, lng

    @property
    def urgent_count(self) -> int:
        return sum(1 for order in self.orders if order.urgency is Urgency.URGENT)


@dataclass(frozen=True)
class CandidateAssignment:
    run_id: str
    driver_id: int
    vehicle_id: int
    estimated_start: int
    estimated_finish: int
    travel_minutes: int
    deadhead_minutes: int
    work_minutes: int
    capacity_waste: int
    preferred_zone_match: int
    continuity_match: int
    objective_score: int
    run_priority_score: int
    efficiency_score: int
    explanation: tuple[str, ...]


@dataclass(frozen=True)
class DispatchStopPlan:
    order_id: int
    sequence: int
    eta: int
    departure: int
    travel_from_previous: int


@dataclass(frozen=True)
class DispatchPlan:
    plan_id: str
    dispatch_date: date
    driver_id: int
    vehicle_id: int
    order_ids: tuple[int, ...]
    total_orders: int
    load_summary: dict[str, float | int]
    zone_code: str
    time_window_start: int
    time_window_end: int
    urgent_order_count: int
    objective_score: int
    explanation: tuple[str, ...]
    stop_sequence: tuple[DispatchStopPlan, ...] = ()
    planned_start: int | None = None
    planned_finish: int | None = None
    etas: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DispatchOrderAssignment:
    order_id: int
    plan_id: str
    dispatch_date: date
    driver_id: int
    vehicle_id: int
    objective_score: int
    postcode: str | None = None
    zone_code: str | None = None
    status: str = "ASSIGNED"
    explanation: tuple[str, ...] = ()
    stop_sequence: int | None = None
    eta: int | None = None
    departure: int | None = None
    planned_start: int | None = None
    planned_finish: int | None = None


@dataclass(frozen=True)
class DispatchException:
    scope: str
    entity_id: str | int
    reason_code: str
    reason_text: str
    suggested_action: str
    is_urgent: bool = False
