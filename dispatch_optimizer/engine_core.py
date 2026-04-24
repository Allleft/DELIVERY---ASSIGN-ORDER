from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace

from .assignment import AssignmentContext, AssignmentSolver, CandidateEnumerator, ScoringPolicy
from .models import (
    DispatchDriver,
    DispatchException,
    DispatchOrder,
    DispatchOrderAssignment,
    DispatchPlan,
    DispatchRun,
    DispatchVehicle,
)
from .preprocess import DispatchInputSnapshotBuilder, SnapshotConfig
from .providers import Geocoder, TravelTimeProvider
from .routing import RoutePlanner
from .run_generation import FleetEnvelope, RunGenerator, RunInsertionPolicy, exists_feasible_vehicle_for_load


@dataclass(frozen=True)
class DispatchEngineConfig:
    bucket_minutes: int = 120
    loose_units_per_tub: int = 4
    max_stops_per_run: int = 12
    max_repair_iterations: int = 3
    insertion_max_cost: float = 60.0
    insertion_max_centroid_km: float = 18.0


@dataclass
class DispatchEngineResult:
    plans: list[DispatchPlan] = field(default_factory=list)
    order_assignments: list[DispatchOrderAssignment] = field(default_factory=list)
    exceptions: list[DispatchException] = field(default_factory=list)
    runs: list[DispatchRun] = field(default_factory=list)


class DispatchEngine:
    def __init__(
        self,
        travel_provider: TravelTimeProvider,
        zone_by_postcode: dict[str, str],
        geocoder: Geocoder | None = None,
        branch_locations: dict[str, tuple[float, float, str]] | None = None,
        config: DispatchEngineConfig | None = None,
    ):
        self.config = config or DispatchEngineConfig()
        self.scoring_policy = ScoringPolicy()
        self.insertion_policy = RunInsertionPolicy(
            insertion_max_cost=self.config.insertion_max_cost,
            insertion_max_centroid_km=self.config.insertion_max_centroid_km,
        )
        snapshot_config = SnapshotConfig(
            loose_units_per_tub=self.config.loose_units_per_tub,
            max_stops_per_run=self.config.max_stops_per_run,
            bucket_minutes=self.config.bucket_minutes,
        )
        normalized_branch_locations = {}
        if branch_locations:
            from .models import LocationRef

            for branch_no, (lat, lng, address) in branch_locations.items():
                normalized_branch_locations[branch_no] = LocationRef(address=address, lat=lat, lng=lng)
        self.snapshot_builder = DispatchInputSnapshotBuilder(
            zone_by_postcode=zone_by_postcode,
            geocoder=geocoder,
            branch_locations=normalized_branch_locations,
            config=snapshot_config,
        )
        self.route_planner = RoutePlanner(travel_provider)
        self.assignment_solver = AssignmentSolver(self.scoring_policy)
        self.candidate_enumerator = CandidateEnumerator(self.route_planner, self.scoring_policy)

    def plan_dispatch(
        self,
        orders: list[DispatchOrder],
        drivers: list[DispatchDriver],
        vehicles: list[DispatchVehicle],
    ) -> DispatchEngineResult:
        snapshot = self.snapshot_builder.build(orders, drivers, vehicles)
        result = DispatchEngineResult(exceptions=list(snapshot.exceptions))
        if not snapshot.orders or not snapshot.drivers or not snapshot.vehicles:
            return result

        fleet_envelope = FleetEnvelope(
            max_capacity=self._max_vehicle_capacity(snapshot.vehicles),
            max_shift_minutes=max(driver.shift_end - driver.shift_start for driver in snapshot.drivers),
        )
        run_generator = RunGenerator(
            self.snapshot_builder,
            fleet_envelope,
            snapshot.drivers,
            snapshot.vehicles,
            self.snapshot_builder.config,
            self.insertion_policy,
        )
        pending_runs = run_generator.generate(snapshot.orders)
        result.runs = list(pending_runs)
        all_drivers_by_id = {driver.driver_id: driver for driver in snapshot.drivers}
        all_vehicles_by_id = {vehicle.vehicle_id: vehicle for vehicle in snapshot.vehicles}
        driver_candidate_counts: dict[int, int] = defaultdict(int)
        driver_selected_counts: dict[int, int] = defaultdict(int)

        repair_iteration = 0
        while pending_runs and repair_iteration <= self.config.max_repair_iterations:
            feasible_runs, rejected = self._filter_runs(pending_runs, snapshot.drivers, snapshot.vehicles)
            result.exceptions.extend(rejected)
            if not feasible_runs:
                break
            feasible_runs, utilization_split_runs = self._maybe_split_for_driver_utilization(
                feasible_runs,
                snapshot.drivers,
                snapshot.vehicles,
            )
            if utilization_split_runs:
                result.runs.extend(utilization_split_runs)

            run_map = {run.run_id: run for run in feasible_runs}
            candidates, rejected_run_ids = self.candidate_enumerator.enumerate(feasible_runs, snapshot.drivers, snapshot.vehicles)
            for candidate in candidates:
                driver_candidate_counts[candidate.driver_id] += 1
            next_pending_runs: list[DispatchRun] = []
            for run_id in rejected_run_ids:
                run = run_map[run_id]
                repaired_runs = self._repair_run(run)
                if repaired_runs:
                    next_pending_runs.extend(repaired_runs)
                    result.runs.extend(repaired_runs)
                else:
                    result.exceptions.append(
                        DispatchException(
                            scope="GROUP",
                            entity_id=self._group_entity_id(run),
                            reason_code="NO_FEASIBLE_ASSIGNMENT",
                            reason_text="No driver-vehicle pair could satisfy capacity and time constraints for this order group.",
                            suggested_action="Review the order group manually or relax constraints.",
                            is_urgent=run.urgent_count > 0,
                        )
                    )

            if not candidates:
                pending_runs = next_pending_runs
                repair_iteration += 1
                continue

            selected_candidates = self.assignment_solver.solve(
                candidates,
                AssignmentContext(
                    drivers_by_id=all_drivers_by_id,
                    vehicles_by_id=all_vehicles_by_id,
                    runs_by_id=run_map,
                ),
            )
            selected_run_ids = {candidate.run_id for candidate in selected_candidates}

            for run in feasible_runs:
                if run.run_id not in selected_run_ids and run.run_id not in rejected_run_ids:
                    result.exceptions.append(
                        DispatchException(
                            scope="GROUP",
                            entity_id=self._group_entity_id(run),
                            reason_code="RUN_UNASSIGNED",
                            reason_text="Order group lost out during global assignment because of overlapping driver/vehicle commitments.",
                            suggested_action="Review unassigned order group manually or add resources.",
                            is_urgent=run.urgent_count > 0,
                        )
                    )

            for candidate in selected_candidates:
                self._append_selected_candidate_output(
                    result,
                    candidate,
                    run_map,
                    driver_selected_counts,
                )

            pending_runs = next_pending_runs
            repair_iteration += 1

        result.exceptions.extend(
            self._build_unused_driver_exceptions(
                snapshot.drivers,
                result.runs,
                driver_candidate_counts,
                driver_selected_counts,
                len(result.plans),
            )
        )
        result.plans, result.order_assignments = self._aggregate_plans_and_assignments(
            result.plans,
            result.order_assignments,
        )

        return result

    @staticmethod
    def _build_trip_plan(run: DispatchRun, candidate) -> DispatchPlan:
        plan_id = DispatchEngine._plan_id_from_run_id(run.run_id)
        base_explanation = list(candidate.explanation)
        base_explanation.append(
            "Trip summary generated without detailed stop-level routing (grouping + assignment semantics)."
        )
        return DispatchPlan(
            plan_id=plan_id,
            dispatch_date=run.dispatch_date,
            driver_id=candidate.driver_id,
            vehicle_id=candidate.vehicle_id,
            order_ids=tuple(order.order_id for order in run.orders),
            total_orders=len(run.orders),
            load_summary=run.load.as_dict(),
            zone_code=run.zone_code,
            time_window_start=run.window_start,
            time_window_end=run.window_end,
            urgent_order_count=run.urgent_count,
            objective_score=candidate.objective_score,
            explanation=tuple(base_explanation),
            stop_sequence=(),
            etas={},
            planned_start=None,
            planned_finish=None,
        )

    @staticmethod
    def _build_order_assignments(plan: DispatchPlan, run: DispatchRun) -> list[DispatchOrderAssignment]:
        return [
            DispatchOrderAssignment(
                order_id=order.order_id,
                plan_id=plan.plan_id,
                dispatch_date=run.dispatch_date,
                driver_id=plan.driver_id,
                vehicle_id=plan.vehicle_id,
                objective_score=plan.objective_score,
                postcode=order.postcode,
                zone_code=order.zone_code,
                status="ASSIGNED",
                explanation=plan.explanation,
                stop_sequence=None,
                eta=None,
                departure=None,
                planned_start=None,
                planned_finish=None,
            )
            for order in run.orders
        ]

    def _append_selected_candidate_output(
        self,
        result: DispatchEngineResult,
        candidate,
        run_map: dict[str, DispatchRun],
        driver_selected_counts: dict[int, int],
    ) -> None:
        driver_selected_counts[candidate.driver_id] += 1
        run = run_map[candidate.run_id]
        dispatch_plan = self._build_trip_plan(run, candidate)
        result.plans.append(dispatch_plan)
        result.order_assignments.extend(self._build_order_assignments(dispatch_plan, run))

    @staticmethod
    def _max_vehicle_capacity(vehicles: list[DispatchVehicle]):
        max_capacity = vehicles[0].capacity
        for vehicle in vehicles[1:]:
            current = vehicle.capacity
            max_capacity = type(max_capacity)(
                kg=max(max_capacity.kg, current.kg),
                pallets=max(max_capacity.pallets, current.pallets),
                tubs=max(max_capacity.tubs, current.tubs),
                loose_units=max(max_capacity.loose_units, current.loose_units),
                trolleys=max(max_capacity.trolleys, current.trolleys),
                stillages=max(max_capacity.stillages, current.stillages),
            )
        return max_capacity

    def _filter_runs(
        self,
        runs: list[DispatchRun],
        drivers: list[DispatchDriver],
        vehicles: list[DispatchVehicle],
    ) -> tuple[list[DispatchRun], list[DispatchException]]:
        feasible: list[DispatchRun] = []
        exceptions: list[DispatchException] = []
        available_driver_ids = {driver.driver_id for driver in drivers}
        for run in runs:
            if run.designated_driver_id is not None and run.designated_driver_id not in available_driver_ids:
                exceptions.append(
                    DispatchException(
                        scope="GROUP",
                        entity_id=self._group_entity_id(run),
                        reason_code="DESIGNATED_DRIVER_UNAVAILABLE",
                        reason_text="At least one order requires a designated driver who is not available.",
                        suggested_action="Release the designated driver constraint or reschedule the order.",
                        is_urgent=run.urgent_count > 0,
                    )
                )
                continue
            if not exists_feasible_vehicle_for_load(run.load, vehicles):
                exceptions.append(
                    DispatchException(
                        scope="GROUP",
                        entity_id=self._group_entity_id(run),
                        reason_code="NO_FEASIBLE_VEHICLE",
                        reason_text="No available vehicle can carry the run load profile.",
                        suggested_action="Split the run manually or release more capacity.",
                        is_urgent=run.urgent_count > 0,
                    )
                )
                continue
            feasible.append(run)
        return feasible, exceptions

    def _repair_run(self, run: DispatchRun) -> list[DispatchRun]:
        if len(run.orders) <= 1:
            return []

        protected_candidates = [
            order for order in run.orders if order.urgency.value == "URGENT" or order.designated_driver_id is not None
        ]
        regular_candidates = [
            order for order in run.orders if order.urgency.value != "URGENT" and order.designated_driver_id is None
        ]
        candidate_pool = regular_candidates if regular_candidates else protected_candidates
        if not candidate_pool:
            candidate_pool = run.orders

        removed_order = max(candidate_pool, key=lambda order: self._repair_penalty(order, run))
        remaining_orders = [order for order in run.orders if order.order_id != removed_order.order_id]
        if not remaining_orders:
            return []

        origin_run_id = run.origin_run_id or run.run_id
        repair_round = run.repair_round + 1
        new_runs: list[DispatchRun] = []
        new_runs.append(
            DispatchRun(
                run_id=run.run_id,
                dispatch_date=run.dispatch_date,
                zone_code=run.zone_code,
                bucket_start=run.bucket_start,
                bucket_end=run.bucket_end,
                orders=remaining_orders,
                load=self._sum_load(remaining_orders),
                estimated_service_minutes=self.snapshot_builder.estimate_service_minutes(len(remaining_orders)),
                designated_driver_id=self._resolve_designated_driver(remaining_orders),
                origin_run_id=origin_run_id,
                repair_round=repair_round,
            )
        )

        isolated_load = self.snapshot_builder.compute_load(removed_order)
        new_runs.append(
            DispatchRun(
                run_id=f"{run.run_id}-R{removed_order.order_id}",
                dispatch_date=removed_order.dispatch_date,
                zone_code=str(removed_order.zone_code),
                bucket_start=removed_order.window_start,
                bucket_end=removed_order.window_end,
                orders=[removed_order],
                load=isolated_load,
                estimated_service_minutes=self.snapshot_builder.estimate_service_minutes(1),
                designated_driver_id=removed_order.designated_driver_id,
                origin_run_id=origin_run_id,
                repair_round=repair_round,
            )
        )
        return new_runs

    def _maybe_split_for_driver_utilization(
        self,
        runs: list[DispatchRun],
        drivers: list[DispatchDriver],
        vehicles: list[DispatchVehicle],
    ) -> tuple[list[DispatchRun], list[DispatchRun]]:
        if not runs:
            return runs, []
        available_drivers = [driver for driver in drivers if driver.is_available]
        if len(available_drivers) <= 1:
            return runs, []

        runs_by_date: dict[object, list[DispatchRun]] = defaultdict(list)
        for run in runs:
            runs_by_date[run.dispatch_date].append(run)

        rebuilt_runs: list[DispatchRun] = []
        generated_runs: list[DispatchRun] = []
        split_guard = max(self.config.max_repair_iterations, 1)
        for dispatch_date, date_runs in runs_by_date.items():
            driver_gap = max(len(available_drivers) - len(date_runs), 0)
            if driver_gap <= 0:
                rebuilt_runs.extend(date_runs)
                continue

            max_splits = min(driver_gap, split_guard)
            working_runs = list(date_runs)
            split_count = 0
            while split_count < max_splits:
                split_candidates = [run for run in working_runs if len(run.orders) >= 2]
                if not split_candidates:
                    break
                did_split = False
                for run in sorted(
                    split_candidates,
                    key=lambda item: (-len(item.orders), item.window_start, item.run_id),
                ):
                    repaired_runs = self._repair_run(run)
                    if len(repaired_runs) != 2:
                        continue
                    if not all(self._is_run_assignable(candidate_run, drivers, vehicles) for candidate_run in repaired_runs):
                        continue
                    working_runs = [item for item in working_runs if item.run_id != run.run_id]
                    working_runs.extend(repaired_runs)
                    generated_runs.extend(repaired_runs)
                    split_count += 1
                    did_split = True
                    break
                if not did_split:
                    break
            rebuilt_runs.extend(working_runs)

        rebuilt_runs.sort(key=lambda item: (item.dispatch_date, item.bucket_start, item.run_id))
        return rebuilt_runs, generated_runs

    def _is_run_assignable(
        self,
        run: DispatchRun,
        drivers: list[DispatchDriver],
        vehicles: list[DispatchVehicle],
    ) -> bool:
        if run.designated_driver_id is not None:
            available_driver_ids = {driver.driver_id for driver in drivers if driver.is_available}
            if run.designated_driver_id not in available_driver_ids:
                return False
        if not exists_feasible_vehicle_for_load(run.load, vehicles):
            return False
        candidates, rejected = self.candidate_enumerator.enumerate([run], drivers, vehicles)
        return bool(candidates) and run.run_id not in rejected

    def _build_unused_driver_exceptions(
        self,
        drivers: list[DispatchDriver],
        runs: list[DispatchRun],
        driver_candidate_counts: dict[int, int],
        driver_selected_counts: dict[int, int],
        assigned_plan_count: int,
    ) -> list[DispatchException]:
        if not drivers:
            return []
        available_drivers = [driver for driver in drivers if driver.is_available]
        if not available_drivers:
            return []

        total_runs = len({run.run_id for run in runs})
        exceptions: list[DispatchException] = []
        for driver in available_drivers:
            selected_count = driver_selected_counts.get(driver.driver_id, 0)
            if selected_count > 0:
                continue
            candidate_count = driver_candidate_counts.get(driver.driver_id, 0)
            driver_label = driver.metadata.get("name") if isinstance(driver.metadata, dict) else None
            if not driver_label:
                driver_label = str(driver.driver_id)
            if candidate_count <= 0:
                if total_runs > 0 and assigned_plan_count >= total_runs:
                    reason_code = "DRIVER_UNUSED_NO_REMAINING_RUN"
                    reason_text = f"Driver {driver_label} stayed idle because no unassigned run remained after global assignment."
                    suggested_action = "Increase runnable order groups or allow additional run splitting for this date."
                else:
                    reason_code = "DRIVER_UNUSED_NO_FEASIBLE_CANDIDATE"
                    reason_text = f"Driver {driver_label} had no feasible candidate under current hard constraints."
                    suggested_action = "Relax time/capacity/designated constraints or provide additional compatible vehicles."
            else:
                reason_code = "DRIVER_UNUSED_OUTSCORED"
                reason_text = f"Driver {driver_label} had feasible candidates but lost against higher-priority global objective."
                suggested_action = "Review scoring weights if stronger load balancing is required."
            exceptions.append(
                DispatchException(
                    scope="DRIVER",
                    entity_id=driver.driver_id,
                    reason_code=reason_code,
                    reason_text=reason_text,
                    suggested_action=suggested_action,
                    is_urgent=False,
                )
            )
        return exceptions

    @staticmethod
    def _group_entity_id(run: DispatchRun) -> str:
        order_ids = ",".join(str(order.order_id) for order in run.orders)
        return f"orders:{order_ids}"

    @staticmethod
    def _plan_id_from_run_id(run_id: str) -> str:
        if run_id.startswith("RUN-"):
            return f"PLAN-{run_id[4:]}"
        return f"PLAN-{run_id}"

    @staticmethod
    def _aggregate_plans_and_assignments(
        plans: list[DispatchPlan],
        order_assignments: list[DispatchOrderAssignment],
    ) -> tuple[list[DispatchPlan], list[DispatchOrderAssignment]]:
        if not plans:
            return plans, order_assignments

        plan_key_to_aggregate: dict[tuple, DispatchPlan] = {}
        original_to_aggregate: dict[str, str] = {}
        ordered_plans = sorted(plans, key=lambda item: (item.dispatch_date, item.driver_id, item.vehicle_id, item.plan_id))

        for plan in ordered_plans:
            key = (plan.dispatch_date, plan.driver_id, plan.vehicle_id)
            existing = plan_key_to_aggregate.get(key)
            if existing is None:
                aggregate_id = f"PLAN-{len(plan_key_to_aggregate) + 1:04d}"
                aggregated = DispatchEngine._build_initial_aggregate_plan(plan, aggregate_id)
                plan_key_to_aggregate[key] = aggregated
                original_to_aggregate[plan.plan_id] = aggregate_id
                continue

            merged = DispatchEngine._merge_aggregate_plan(existing, plan)
            plan_key_to_aggregate[key] = merged
            original_to_aggregate[plan.plan_id] = existing.plan_id

        aggregated_plans = list(plan_key_to_aggregate.values())
        remapped_assignments = DispatchEngine._remap_and_sort_assignments(order_assignments, original_to_aggregate)
        return aggregated_plans, remapped_assignments

    @staticmethod
    def _build_initial_aggregate_plan(plan: DispatchPlan, aggregate_id: str) -> DispatchPlan:
        return DispatchPlan(
            plan_id=aggregate_id,
            dispatch_date=plan.dispatch_date,
            driver_id=plan.driver_id,
            vehicle_id=plan.vehicle_id,
            order_ids=tuple(plan.order_ids),
            total_orders=plan.total_orders,
            load_summary=dict(plan.load_summary),
            zone_code=plan.zone_code,
            time_window_start=plan.time_window_start,
            time_window_end=plan.time_window_end,
            urgent_order_count=plan.urgent_order_count,
            objective_score=plan.objective_score,
            explanation=tuple(dict.fromkeys(plan.explanation)),
            stop_sequence=(),
            planned_start=None,
            planned_finish=None,
            etas={},
        )

    @staticmethod
    def _merge_aggregate_plan(existing: DispatchPlan, plan: DispatchPlan) -> DispatchPlan:
        merged_order_ids = tuple(sorted(set(existing.order_ids + plan.order_ids)))
        merged_load = DispatchEngine._merge_load_summary(existing.load_summary, plan.load_summary)
        merged_zone = existing.zone_code if existing.zone_code == plan.zone_code else "MULTI_ZONE"
        merged_explanation = tuple(dict.fromkeys(existing.explanation + plan.explanation))
        return DispatchPlan(
            plan_id=existing.plan_id,
            dispatch_date=existing.dispatch_date,
            driver_id=existing.driver_id,
            vehicle_id=existing.vehicle_id,
            order_ids=merged_order_ids,
            total_orders=len(merged_order_ids),
            load_summary=merged_load,
            zone_code=merged_zone,
            time_window_start=min(existing.time_window_start, plan.time_window_start),
            time_window_end=max(existing.time_window_end, plan.time_window_end),
            urgent_order_count=existing.urgent_order_count + plan.urgent_order_count,
            objective_score=existing.objective_score + plan.objective_score,
            explanation=merged_explanation,
            stop_sequence=(),
            planned_start=None,
            planned_finish=None,
            etas={},
        )

    @staticmethod
    def _merge_load_summary(existing_load: dict, incoming_load: dict) -> dict:
        merged_load = dict(existing_load)
        for field_name in ("kg", "pallets", "tubs", "loose_units", "trolleys", "stillages"):
            merged_load[field_name] = merged_load.get(field_name, 0) + incoming_load.get(field_name, 0)
        if "kg" in merged_load:
            merged_load["kg"] = round(float(merged_load["kg"]), 2)
        return merged_load

    @staticmethod
    def _remap_and_sort_assignments(
        order_assignments: list[DispatchOrderAssignment],
        original_to_aggregate: dict[str, str],
    ) -> list[DispatchOrderAssignment]:
        remapped_assignments = [
            replace(
                assignment,
                plan_id=original_to_aggregate.get(assignment.plan_id, assignment.plan_id),
            )
            for assignment in order_assignments
        ]
        remapped_assignments.sort(key=lambda item: (item.dispatch_date, item.driver_id, item.vehicle_id, item.order_id))
        return remapped_assignments

    def _repair_penalty(self, order: DispatchOrder, run: DispatchRun) -> float:
        distance = self._distance_from_centroid(order, run)
        window_span = max(order.window_end - order.window_start, 1)
        time_impact = 1.0 / window_span
        total_load = self._sum_load(run.orders)
        order_load = self.snapshot_builder.compute_load(order)
        load_share = self._load_share(order_load, total_load)
        non_urgent_bonus = 1.0 if order.urgency.value != "URGENT" else 0.0
        non_designated_bonus = 1.0 if order.designated_driver_id is None else 0.0
        return (
            distance * 3.0
            + time_impact * 120.0
            + load_share * 50.0
            + non_urgent_bonus * 30.0
            + non_designated_bonus * 20.0
        )

    def _distance_from_centroid(self, order: DispatchOrder, run: DispatchRun) -> float:
        if order.lat is None or order.lng is None:
            return 0.0
        centroid = run.centroid
        if centroid is None:
            return 0.0
        return abs(order.lat - centroid[0]) + abs(order.lng - centroid[1])

    def _sum_load(self, orders: list[DispatchOrder]):
        load = self.snapshot_builder.compute_load(orders[0])
        for order in orders[1:]:
            load = load + self.snapshot_builder.compute_load(order)
        return load

    @staticmethod
    def _load_share(order_load, total_load) -> float:
        total = (
            (total_load.kg if total_load.kg > 0 else 0.0)
            + total_load.pallets
            + total_load.tubs
            + total_load.loose_units
            + total_load.trolleys
            + total_load.stillages
        )
        if total <= 0:
            return 0.0
        part = (
            (order_load.kg if order_load.kg > 0 else 0.0)
            + order_load.pallets
            + order_load.tubs
            + order_load.loose_units
            + order_load.trolleys
            + order_load.stillages
        )
        return part / total

    @staticmethod
    def _resolve_designated_driver(orders: list[DispatchOrder]) -> int | None:
        designated = {order.designated_driver_id for order in orders if order.designated_driver_id is not None}
        if len(designated) == 1:
            return designated.pop()
        return None
