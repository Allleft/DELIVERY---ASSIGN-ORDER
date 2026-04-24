from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil

from .models import (
    FIXED_STOP_MINUTES,
    DispatchDriver,
    DispatchException,
    DispatchOrder,
    DispatchVehicle,
    LoadType,
    LoadVector,
    LocationRef,
)
from .providers import Geocoder


@dataclass(frozen=True)
class SnapshotConfig:
    loose_units_per_tub: int = 4
    max_stops_per_run: int = 12
    bucket_minutes: int = 120


@dataclass
class SnapshotResult:
    orders: list[DispatchOrder]
    drivers: list[DispatchDriver]
    vehicles: list[DispatchVehicle]
    exceptions: list[DispatchException] = field(default_factory=list)


class DispatchInputSnapshotBuilder:
    def __init__(
        self,
        zone_by_postcode: dict[str, str],
        geocoder: Geocoder | None = None,
        branch_locations: dict[str, LocationRef] | None = None,
        config: SnapshotConfig | None = None,
    ):
        self.zone_by_postcode = zone_by_postcode
        self.geocoder = geocoder
        self.branch_locations = branch_locations or {}
        self.config = config or SnapshotConfig()

    def build(
        self,
        orders: list[DispatchOrder],
        drivers: list[DispatchDriver],
        vehicles: list[DispatchVehicle],
    ) -> SnapshotResult:
        result = SnapshotResult(orders=[], drivers=[], vehicles=[vehicle for vehicle in vehicles if vehicle.is_available])
        for order in orders:
            normalized = self._normalize_order(order)
            if isinstance(normalized, DispatchException):
                result.exceptions.append(normalized)
            else:
                result.orders.append(normalized)

        for driver in drivers:
            normalized_driver = self._normalize_driver(driver)
            if isinstance(normalized_driver, DispatchException):
                result.exceptions.append(normalized_driver)
            elif normalized_driver.is_available:
                result.drivers.append(normalized_driver)

        if not result.drivers:
            result.exceptions.append(
                DispatchException(
                    scope="SYSTEM",
                    entity_id="drivers",
                    reason_code="NO_AVAILABLE_DRIVERS",
                    reason_text="No available drivers were found in the dispatch snapshot.",
                    suggested_action="Update shift availability before rerunning dispatch.",
                )
            )

        if not result.vehicles:
            result.exceptions.append(
                DispatchException(
                    scope="SYSTEM",
                    entity_id="vehicles",
                    reason_code="NO_AVAILABLE_VEHICLES",
                    reason_text="No available vehicles were found in the dispatch snapshot.",
                    suggested_action="Update vehicle availability before rerunning dispatch.",
                )
            )

        return result

    def compute_load(self, order: DispatchOrder) -> LoadVector:
        tubs = 0
        loose_units = 0
        if order.load_type is LoadType.MIXED:
            tubs = ceil(order.bag_count / self.config.loose_units_per_tub)
        elif order.load_type is LoadType.LOOSE:
            loose_units = order.bag_count
        return LoadVector(
            kg=order.kg_count,
            pallets=order.pallet_count,
            tubs=tubs,
            loose_units=loose_units,
        )

    def _normalize_order(self, order: DispatchOrder) -> DispatchOrder | DispatchException:
        lat = order.lat
        lng = order.lng
        if not order.delivery_address:
            return DispatchException(
                scope="ORDER",
                entity_id=order.order_id,
                reason_code="MISSING_ADDRESS",
                reason_text="Order is missing a delivery address and cannot be routed.",
                suggested_action="Populate delivery address and rerun dispatch.",
                is_urgent=order.urgency.value == "URGENT",
            )

        if (lat is None or lng is None) and self.geocoder is not None:
            location = self.geocoder.geocode(order.delivery_address)
            if location is not None:
                lat = location.lat
                lng = location.lng

        zone_code = order.zone_code.strip() if isinstance(order.zone_code, str) and order.zone_code.strip() else None
        postcode = str(order.postcode).strip() if order.postcode is not None else ""
        mapped_zone = self.zone_by_postcode.get(postcode) if postcode else None
        if mapped_zone:
            zone_code = str(mapped_zone).strip()

        if zone_code is None:
            return DispatchException(
                scope="ORDER",
                entity_id=order.order_id,
                reason_code="POSTCODE_NOT_MAPPED",
                reason_text="No zone mapping found for postcode.",
                suggested_action="Populate postcode and update zone_by_postcode mapping.",
                is_urgent=order.urgency.value == "URGENT",
            )

        if order.window_start >= order.window_end:
            return DispatchException(
                scope="ORDER",
                entity_id=order.order_id,
                reason_code="INVALID_TIME_WINDOW",
                reason_text="Order time window is invalid.",
                suggested_action="Fix opening hours before rerunning dispatch.",
                is_urgent=order.urgency.value == "URGENT",
            )

        if lat is None or lng is None:
            return DispatchException(
                scope="ORDER",
                entity_id=order.order_id,
                reason_code="MISSING_COORDINATES",
                reason_text="Order could not be geocoded into lat/lng.",
                suggested_action="Provide coordinates or configure a geocoder.",
                is_urgent=order.urgency.value == "URGENT",
            )

        return DispatchOrder(
            order_id=order.order_id,
            dispatch_date=order.dispatch_date,
            delivery_address=order.delivery_address,
            lat=lat,
            lng=lng,
            zone_code=zone_code,
            urgency=order.urgency,
            window_start=order.window_start,
            window_end=order.window_end,
            designated_driver_id=order.designated_driver_id,
            load_type=order.load_type,
            kg_count=order.kg_count,
            pallet_count=order.pallet_count,
            bag_count=order.bag_count,
            postcode=order.postcode,
            suburb=order.suburb,
            metadata=order.metadata,
        )

    def _normalize_driver(self, driver: DispatchDriver) -> DispatchDriver | DispatchException:
        start_ref = self._resolve_location(driver.start_location, driver.start_lat, driver.start_lng, driver.branch_no)
        end_ref = self._resolve_location(driver.end_location, driver.end_lat, driver.end_lng, driver.branch_no)
        if start_ref is None or end_ref is None:
            return DispatchException(
                scope="DRIVER",
                entity_id=driver.driver_id,
                reason_code="MISSING_DRIVER_LOCATION",
                reason_text="Driver start or end location could not be resolved.",
                suggested_action="Provide start/end coordinates or configure a branch depot location.",
            )

        if driver.shift_start >= driver.shift_end:
            return DispatchException(
                scope="DRIVER",
                entity_id=driver.driver_id,
                reason_code="INVALID_SHIFT",
                reason_text="Driver shift start must be earlier than shift end.",
                suggested_action="Fix driver shift availability before rerunning dispatch.",
            )

        return DispatchDriver(
            driver_id=driver.driver_id,
            shift_start=driver.shift_start,
            shift_end=driver.shift_end,
            is_available=driver.is_available,
            start_location=start_ref.address,
            end_location=end_ref.address,
            preferred_zone_codes=tuple(
                str(zone_code).strip()
                for zone_code in driver.preferred_zone_codes
                if str(zone_code).strip()
            ),
            historical_vehicle_ids=driver.historical_vehicle_ids,
            branch_no=driver.branch_no,
            start_lat=start_ref.lat,
            start_lng=start_ref.lng,
            end_lat=end_ref.lat,
            end_lng=end_ref.lng,
            metadata=driver.metadata,
        )

    @staticmethod
    def estimate_service_minutes(stop_count: int) -> int:
        return max(int(stop_count), 0) * FIXED_STOP_MINUTES

    def _resolve_location(
        self,
        address: str,
        lat: float | None,
        lng: float | None,
        branch_no: str | None,
    ) -> LocationRef | None:
        if lat is not None and lng is not None:
            return LocationRef(address=address, lat=lat, lng=lng)
        if address and self.geocoder is not None:
            geocoded = self.geocoder.geocode(address)
            if geocoded is not None:
                return geocoded
        if branch_no and branch_no in self.branch_locations:
            depot = self.branch_locations[branch_no]
            if address:
                return LocationRef(address=address, lat=depot.lat, lng=depot.lng)
            return depot
        return None
