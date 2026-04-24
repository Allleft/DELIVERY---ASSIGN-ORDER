from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import sqrt

from .models import DispatchDriver, DispatchOrder, DispatchRun, DispatchVehicle, LoadVector
from .preprocess import DispatchInputSnapshotBuilder, SnapshotConfig


@dataclass(frozen=True)
class FleetEnvelope:
    max_capacity: LoadVector
    max_shift_minutes: int


@dataclass(frozen=True)
class RunInsertionPolicy:
    insertion_max_cost: float = 60.0
    insertion_max_centroid_km: float = 18.0
    distance_scale_km: float = 20.0
    distance_weight: float = 0.35
    window_weight: float = 0.30
    service_weight: float = 0.20
    capacity_weight: float = 0.15


def exists_feasible_vehicle_for_load(load: LoadVector, vehicles: list[DispatchVehicle]) -> bool:
    return any(load.fits_in(vehicle.capacity) for vehicle in vehicles if vehicle.is_available)


class RunGenerator:
    def __init__(
        self,
        snapshot_builder: DispatchInputSnapshotBuilder,
        fleet_envelope: FleetEnvelope,
        drivers: list[DispatchDriver],
        vehicles: list[DispatchVehicle],
        config: SnapshotConfig | None = None,
        insertion_policy: RunInsertionPolicy | None = None,
    ):
        self.snapshot_builder = snapshot_builder
        self.fleet_envelope = fleet_envelope
        self.drivers = [driver for driver in drivers if driver.is_available]
        self.vehicles = vehicles
        self.config = config or SnapshotConfig()
        self.insertion_policy = insertion_policy or RunInsertionPolicy()
        self._capacity_scale = max(self._load_scale(self.fleet_envelope.max_capacity), 1.0)
        self._pair_feasibility_cache: dict[tuple, bool] = {}

    def generate(self, orders: list[DispatchOrder]) -> list[DispatchRun]:
        grouped: dict[tuple, list[DispatchOrder]] = defaultdict(list)
        for order in orders:
            bucket_start = (order.window_start // self.config.bucket_minutes) * self.config.bucket_minutes
            bucket_end = min(bucket_start + self.config.bucket_minutes, 24 * 60)
            grouped[(order.dispatch_date, order.zone_code, bucket_start, bucket_end)].append(order)

        runs: list[DispatchRun] = []
        run_counter = 1
        for (dispatch_date, zone_code, bucket_start, bucket_end), bucket_orders in sorted(grouped.items()):
            ordered_bucket = sorted(bucket_orders, key=self._priority_key)
            bucket_runs: list[DispatchRun] = []
            for order in ordered_bucket:
                load = self.snapshot_builder.compute_load(order)
                best_run: DispatchRun | None = None
                best_cost: float | None = None
                for candidate_run in bucket_runs:
                    if not self._can_fit_order(candidate_run, order, load):
                        continue
                    new_load = candidate_run.load + load
                    if not exists_feasible_vehicle_for_load(new_load, self.vehicles):
                        continue
                    if not self._exists_real_driver_vehicle_pair(
                        load=new_load,
                        designated_driver_id=(
                            candidate_run.designated_driver_id
                            if candidate_run.designated_driver_id is not None
                            else order.designated_driver_id
                        ),
                        window_start=min(candidate_run.window_start, order.window_start),
                        window_end=max(candidate_run.window_end, order.window_end),
                        stop_count=len(candidate_run.orders) + 1,
                    ):
                        continue
                    insertion_cost = self._insertion_cost(candidate_run, order, new_load)
                    if insertion_cost == float("inf"):
                        continue
                    if best_cost is None or insertion_cost < best_cost:
                        best_cost = insertion_cost
                        best_run = candidate_run

                if best_run is not None and best_cost is not None and best_cost <= self.insertion_policy.insertion_max_cost:
                    best_run.orders.append(order)
                    best_run.load = best_run.load + load
                    best_run.estimated_service_minutes = self.snapshot_builder.estimate_service_minutes(len(best_run.orders))
                    if best_run.designated_driver_id is None:
                        best_run.designated_driver_id = order.designated_driver_id
                else:
                    bucket_runs.append(
                        DispatchRun(
                            run_id=f"RUN-{run_counter:04d}",
                            dispatch_date=dispatch_date,
                            zone_code=str(zone_code),
                            bucket_start=bucket_start,
                            bucket_end=bucket_end,
                            orders=[order],
                            load=load,
                            estimated_service_minutes=self.snapshot_builder.estimate_service_minutes(1),
                            designated_driver_id=order.designated_driver_id,
                        )
                    )
                    run_counter += 1
            runs.extend(bucket_runs)
        return runs

    def _can_fit_order(self, run: DispatchRun, order: DispatchOrder, load: LoadVector) -> bool:
        if len(run.orders) >= self.config.max_stops_per_run:
            return False
        if run.designated_driver_id and order.designated_driver_id and run.designated_driver_id != order.designated_driver_id:
            return False
        new_load = run.load + load
        if not new_load.fits_in(self.fleet_envelope.max_capacity):
            return False
        estimated_service = self.snapshot_builder.estimate_service_minutes(len(run.orders) + 1)
        estimated_minutes = estimated_service + self._intra_run_travel_buffer(len(run.orders) + 1)
        if estimated_minutes > self.fleet_envelope.max_shift_minutes:
            return False
        return True

    def _insertion_cost(self, run: DispatchRun, order: DispatchOrder, new_load: LoadVector) -> float:
        overlap = min(run.window_end, order.window_end) - max(run.window_start, order.window_start)
        if overlap <= 0:
            return float("inf")

        run_window_minutes = max(run.window_end - run.window_start, 1)
        order_window_minutes = max(order.window_end - order.window_start, 1)
        overlap_base = max(min(run_window_minutes, order_window_minutes), 1)
        n_window = self._clamp(1.0 - (overlap / overlap_base))

        distance_km = self._distance_to_centroid_km(order, run)
        if distance_km > self.insertion_policy.insertion_max_centroid_km:
            return float("inf")
        n_dist = self._clamp(distance_km / self.insertion_policy.distance_scale_km)

        current_stop_count = len(run.orders)
        delta_buffer = self._intra_run_travel_buffer(current_stop_count + 1) - self._intra_run_travel_buffer(current_stop_count)
        current_service = self.snapshot_builder.estimate_service_minutes(current_stop_count)
        next_service = self.snapshot_builder.estimate_service_minutes(current_stop_count + 1)
        delta_service = max((next_service - current_service) + delta_buffer, 0)
        n_service = self._clamp(delta_service / max(self.fleet_envelope.max_shift_minutes, 1))

        current_waste = run.load.waste_against(self.fleet_envelope.max_capacity)
        new_waste = new_load.waste_against(self.fleet_envelope.max_capacity)
        delta_waste = abs(new_waste - current_waste)
        n_capacity = self._clamp(delta_waste / self._capacity_scale)

        return 100.0 * (
            self.insertion_policy.distance_weight * n_dist
            + self.insertion_policy.window_weight * n_window
            + self.insertion_policy.service_weight * n_service
            + self.insertion_policy.capacity_weight * n_capacity
        )

    @staticmethod
    def _distance_to_centroid_km(order: DispatchOrder, run: DispatchRun) -> float:
        if order.lat is None or order.lng is None:
            return 0.0
        centroid = run.centroid
        if centroid is None:
            return 0.0
        lat_delta = (order.lat - centroid[0]) * 111.0
        lng_delta = (order.lng - centroid[1]) * 111.0
        return sqrt(lat_delta * lat_delta + lng_delta * lng_delta)

    @staticmethod
    def _load_scale(load: LoadVector) -> float:
        return (
            (load.kg if load.kg > 0 else 0.0)
            + load.pallets
            + load.tubs
            + load.loose_units
            + load.trolleys
            + load.stillages
        )

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    @staticmethod
    def _priority_key(order: DispatchOrder) -> tuple[int, int, int, int]:
        urgency_rank = 0 if order.urgency.value == "URGENT" else 1
        designated_rank = 0 if order.designated_driver_id is not None else 1
        size_rank = -(order.pallet_count * 10 + order.bag_count + int(order.kg_count))
        return urgency_rank, order.window_end, designated_rank, size_rank

    @staticmethod
    def _intra_run_travel_buffer(stop_count: int) -> int:
        return max((stop_count - 1) * 15, 0)

    def _exists_real_driver_vehicle_pair(
        self,
        load: LoadVector,
        designated_driver_id: int | None,
        window_start: int,
        window_end: int,
        stop_count: int,
    ) -> bool:
        key = (
            round(load.kg, 2),
            load.pallets,
            load.tubs,
            load.loose_units,
            load.trolleys,
            load.stillages,
            designated_driver_id,
            int(window_start),
            int(window_end),
            int(stop_count),
        )
        cached = self._pair_feasibility_cache.get(key)
        if cached is not None:
            return cached

        feasible_vehicles = [vehicle for vehicle in self.vehicles if vehicle.is_available and load.fits_in(vehicle.capacity)]
        if not feasible_vehicles:
            self._pair_feasibility_cache[key] = False
            return False

        estimated_service_minutes = self.snapshot_builder.estimate_service_minutes(stop_count)
        estimated_trip_minutes = estimated_service_minutes + self._intra_run_travel_buffer(stop_count) + 24
        latest_window_finish = window_end + min(90, max(20, stop_count * 8))

        for driver in self.drivers:
            if designated_driver_id is not None and driver.driver_id != designated_driver_id:
                continue
            estimated_start = max(driver.shift_start, window_start)
            estimated_finish = estimated_start + estimated_trip_minutes
            if estimated_finish > driver.shift_end:
                continue
            if estimated_finish > latest_window_finish:
                continue
            self._pair_feasibility_cache[key] = True
            return True

        self._pair_feasibility_cache[key] = False
        return False
