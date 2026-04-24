from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from math import sqrt

from .models import CandidateAssignment, DispatchDriver, DispatchRun, DispatchVehicle, LoadType

try:
    from ortools.sat.python import cp_model

    ORTOOLS_CP_SAT_AVAILABLE = True
except ModuleNotFoundError:
    ORTOOLS_CP_SAT_AVAILABLE = False


@dataclass(frozen=True)
class AssignmentContext:
    drivers_by_id: dict[int, DispatchDriver]
    vehicles_by_id: dict[int, DispatchVehicle]
    runs_by_id: dict[str, DispatchRun]


@dataclass(frozen=True)
class ScoringPolicy:
    run_priority_scale: int = 10_000
    urgent_run_bonus: int = 300
    designated_run_bonus: int = 180
    load_type_on_pallet_bonus: int = 90
    load_type_mixed_bonus: int = 55
    load_type_loose_bonus: int = 25
    time_window_pressure_cap_minutes: int = 180
    time_window_pressure_weight: int = 2
    travel_penalty_per_min: int = 120
    deadhead_penalty_per_min: int = 45
    capacity_waste_penalty_per_unit: int = 1
    preferred_zone_bonus: int = 3000
    zone_mismatch_penalty: int = 2500
    continuity_bonus: int = 160
    vehicle_switch_penalty: int = 2000
    vehicle_switch_proxy_penalty: int = 2000
    unused_driver_bonus: int = 800
    driver_run_balance_weight: int = 180
    driver_balance_penalty_per_min: int = 25
    cp_sat_time_limit_seconds: int = 5


class CandidateEnumerator:
    def __init__(self, route_planner=None, scoring_policy: ScoringPolicy | None = None):
        # route_planner is kept as an optional compatibility argument; candidate feasibility
        # is now based on coarse trip-level estimation and no longer requires detailed routing.
        self.route_planner = route_planner
        self.scoring_policy = scoring_policy or ScoringPolicy()
        self._average_speed_kph = 35.0
        self._min_leg_minutes = 3
        self._default_deadhead_leg_minutes = 12
        self._intra_stop_buffer_minutes = 12
        self._boundary_shift_margin_minutes = 30
        self._boundary_window_margin_minutes = 20
        self._tight_window_minutes = 120

    def enumerate(
        self,
        runs: list[DispatchRun],
        drivers: list[DispatchDriver],
        vehicles: list[DispatchVehicle],
    ) -> tuple[list[CandidateAssignment], list[str]]:
        candidates: list[CandidateAssignment] = []
        rejected_runs: list[str] = []
        for run in runs:
            run_priority_score, run_priority_reasons = self._run_priority_score(run)
            time_window_pressure = self._time_window_pressure(run)
            run_candidates: list[CandidateAssignment] = []
            for driver in drivers:
                if not driver.is_available:
                    continue
                if run.designated_driver_id is not None and driver.driver_id != run.designated_driver_id:
                    continue
                coarse_estimate = self._estimate_trip_window(run, driver)
                if coarse_estimate is None:
                    continue
                estimated_start, estimated_finish, travel_minutes, deadhead_minutes, work_minutes = coarse_estimate
                for vehicle in vehicles:
                    if not vehicle.is_available:
                        continue
                    if not run.load.fits_in(vehicle.capacity):
                        continue
                    candidate_estimated_start = estimated_start
                    candidate_estimated_finish = estimated_finish
                    candidate_travel_minutes = travel_minutes
                    candidate_deadhead_minutes = deadhead_minutes
                    candidate_work_minutes = work_minutes
                    route_validated = False
                    if self._needs_route_validation(run, driver, candidate_estimated_finish):
                        route = self.route_planner.plan(run, driver, vehicle) if self.route_planner is not None else None
                        if route is None or not route.feasible:
                            continue
                        route_validated = True
                        candidate_estimated_start = route.planned_start
                        candidate_estimated_finish = route.planned_finish
                        candidate_travel_minutes = route.travel_minutes
                        candidate_deadhead_minutes = route.deadhead_minutes
                        candidate_work_minutes = max(route.planned_finish - route.planned_start, 0)
                    preferred_zone_match = 1 if run.zone_code in driver.preferred_zone_codes else 0
                    zone_mismatch = 1 if driver.preferred_zone_codes and not preferred_zone_match else 0
                    continuity_match = 1 if vehicle.vehicle_id in driver.historical_vehicle_ids else 0
                    capacity_waste = int(round(run.load.waste_against(vehicle.capacity) * 100))
                    efficiency_score = self._efficiency_score(
                        candidate_travel_minutes,
                        candidate_deadhead_minutes,
                        capacity_waste,
                        preferred_zone_match,
                        zone_mismatch,
                        continuity_match,
                    )
                    objective_score = run_priority_score * self.scoring_policy.run_priority_scale + efficiency_score
                    explanation = [
                        f"Run {run.run_id} fits vehicle {vehicle.vehicle_id} capacity.",
                        f"Estimated trip workload {work_minutes} min (coarse) within shift.",
                        f"Scored with unified business policy: priority={run_priority_score}, efficiency={efficiency_score}.",
                    ]
                    explanation.extend(run_priority_reasons)
                    explanation.append(
                        f"Trip window check start={candidate_estimated_start} finish={candidate_estimated_finish}."
                    )
                    if preferred_zone_match:
                        explanation.append("Preferred zone matched for this driver.")
                    elif zone_mismatch:
                        explanation.append("Driver preferred zone mismatch applied.")
                    else:
                        explanation.append("Preferred zone not matched for this driver.")
                    if continuity_match:
                        explanation.append("Historical driver-vehicle pairing preserved.")
                    explanation.append(f"Time-window pressure index={time_window_pressure}.")
                    explanation.append(f"Capacity waste index={capacity_waste}.")
                    if route_validated:
                        explanation.append("Validated with route-level feasibility check for high-priority/boundary candidate.")
                    run_candidates.append(
                        CandidateAssignment(
                            run_id=run.run_id,
                            driver_id=driver.driver_id,
                            vehicle_id=vehicle.vehicle_id,
                            estimated_start=candidate_estimated_start,
                            estimated_finish=candidate_estimated_finish,
                            travel_minutes=candidate_travel_minutes,
                            deadhead_minutes=candidate_deadhead_minutes,
                            work_minutes=candidate_work_minutes,
                            capacity_waste=capacity_waste,
                            preferred_zone_match=preferred_zone_match,
                            continuity_match=continuity_match,
                            run_priority_score=run_priority_score,
                            efficiency_score=efficiency_score,
                            objective_score=objective_score,
                            explanation=tuple(explanation),
                        )
                    )
            if not run_candidates:
                rejected_runs.append(run.run_id)
            else:
                candidates.extend(run_candidates)
        return candidates, rejected_runs

    def _needs_route_validation(self, run: DispatchRun, driver: DispatchDriver, coarse_finish: int) -> bool:
        if self.route_planner is None:
            return False
        if run.urgent_count > 0:
            return True
        if run.designated_driver_id is not None:
            return True
        if (run.window_end - run.window_start) <= self._tight_window_minutes:
            return True
        if (driver.shift_end - coarse_finish) <= self._boundary_shift_margin_minutes:
            return True
        if ((run.window_end + self._window_slack_minutes(run)) - coarse_finish) <= self._boundary_window_margin_minutes:
            return True
        return False

    def _estimate_trip_window(
        self,
        run: DispatchRun,
        driver: DispatchDriver,
    ) -> tuple[int, int, int, int, int] | None:
        deadhead_start = self._estimate_leg_minutes(
            driver.start_lat,
            driver.start_lng,
            *(run.centroid if run.centroid is not None else (None, None)),
        )
        deadhead_end = self._estimate_leg_minutes(
            *(run.centroid if run.centroid is not None else (None, None)),
            driver.end_lat,
            driver.end_lng,
        )
        intra_trip = max(len(run.orders) - 1, 0) * self._intra_stop_buffer_minutes
        travel_minutes = deadhead_start + intra_trip + deadhead_end
        work_minutes = run.estimated_service_minutes + travel_minutes

        estimated_start = max(driver.shift_start, run.window_start)
        estimated_finish = estimated_start + work_minutes
        latest_window_finish = run.window_end + self._window_slack_minutes(run)

        if estimated_finish > driver.shift_end:
            return None
        if estimated_finish > latest_window_finish:
            return None
        return estimated_start, estimated_finish, travel_minutes, deadhead_start, work_minutes

    def _window_slack_minutes(self, run: DispatchRun) -> int:
        return min(90, max(20, len(run.orders) * 8))

    def _estimate_leg_minutes(
        self,
        from_lat: float | None,
        from_lng: float | None,
        to_lat: float | None,
        to_lng: float | None,
    ) -> int:
        if None in (from_lat, from_lng, to_lat, to_lng):
            return self._default_deadhead_leg_minutes
        lat_delta = (float(from_lat) - float(to_lat)) * 111.0
        lng_delta = (float(from_lng) - float(to_lng)) * 111.0
        km = sqrt(lat_delta * lat_delta + lng_delta * lng_delta)
        minutes = int(round((km / self._average_speed_kph) * 60))
        return max(minutes, self._min_leg_minutes)

    def _run_priority_score(self, run: DispatchRun) -> tuple[int, list[str]]:
        score = 0
        reasons: list[str] = []
        if run.urgent_count > 0:
            score += self.scoring_policy.urgent_run_bonus
            reasons.append("Urgent run priority applied.")
        if run.designated_driver_id is not None:
            score += self.scoring_policy.designated_run_bonus
            reasons.append("Designated driver requirement prioritized.")

        dominant_load_bonus, load_reason = self._load_type_priority(run)
        score += dominant_load_bonus
        if load_reason:
            reasons.append(load_reason)

        pressure = self._time_window_pressure(run)
        if pressure > 0:
            pressure_score = pressure * self.scoring_policy.time_window_pressure_weight
            score += pressure_score
            reasons.append(f"Tight time-window pressure bonus applied ({pressure_score}).")
        return score, reasons

    def _load_type_priority(self, run: DispatchRun) -> tuple[int, str]:
        load_rank = {
            LoadType.ON_PALLET: (self.scoring_policy.load_type_on_pallet_bonus, "ON_PALLET load profile prioritized."),
            LoadType.MIXED: (self.scoring_policy.load_type_mixed_bonus, "MIXED load profile prioritized."),
            LoadType.LOOSE: (self.scoring_policy.load_type_loose_bonus, "LOOSE load profile prioritized."),
        }
        best_bonus = self.scoring_policy.load_type_loose_bonus
        best_reason = "LOOSE load profile prioritized."
        for order in run.orders:
            bonus, reason = load_rank.get(order.load_type, (self.scoring_policy.load_type_loose_bonus, "LOOSE load profile prioritized."))
            if bonus > best_bonus:
                best_bonus = bonus
                best_reason = reason
        return best_bonus, best_reason

    def _time_window_pressure(self, run: DispatchRun) -> int:
        span = max(run.window_end - run.window_start, 1)
        return max(self.scoring_policy.time_window_pressure_cap_minutes - span, 0)

    def _efficiency_score(
        self,
        travel_minutes: int,
        deadhead_minutes: int,
        capacity_waste: int,
        preferred_zone_match: int,
        zone_mismatch: int,
        continuity_match: int,
    ) -> int:
        return (
            -(travel_minutes * self.scoring_policy.travel_penalty_per_min)
            - (deadhead_minutes * self.scoring_policy.deadhead_penalty_per_min)
            - (capacity_waste * self.scoring_policy.capacity_waste_penalty_per_unit)
            + (preferred_zone_match * self.scoring_policy.preferred_zone_bonus)
            - (zone_mismatch * self.scoring_policy.zone_mismatch_penalty)
            + (continuity_match * self.scoring_policy.continuity_bonus)
        )


class AssignmentSolver:
    def __init__(self, scoring_policy: ScoringPolicy | None = None):
        self.scoring_policy = scoring_policy or ScoringPolicy()

    def solve(self, candidates: list[CandidateAssignment], context: AssignmentContext) -> list[CandidateAssignment]:
        if ORTOOLS_CP_SAT_AVAILABLE:
            selected = self._solve_with_cp_sat(candidates, context)
        else:
            selected = self._solve_greedily(candidates, context)
        selected = self._annotate_driver_utilization_explanations(selected, context)
        return self._annotate_vehicle_switch_explanations(selected, candidates, context)

    def _solve_stage(
        self,
        model: "cp_model.CpModel",
        objective_expr,
        *,
        maximize: bool,
    ) -> tuple[bool, int]:
        if maximize:
            model.Maximize(objective_expr)
        else:
            model.Minimize(objective_expr)
        stage_solver = cp_model.CpSolver()
        stage_solver.parameters.max_time_in_seconds = self.scoring_policy.cp_sat_time_limit_seconds
        stage_status = stage_solver.Solve(model)
        if stage_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return False, 0
        return True, int(round(stage_solver.ObjectiveValue()))

    def _lock_stage_or_none(
        self,
        model: "cp_model.CpModel",
        objective_expr,
        *,
        maximize: bool,
    ) -> int | None:
        ok, best_value = self._solve_stage(model, objective_expr, maximize=maximize)
        if not ok:
            return None
        if maximize:
            model.Add(objective_expr >= best_value)
        else:
            model.Add(objective_expr <= best_value)
        return best_value

    def _solve_with_cp_sat(
        self,
        candidates: list[CandidateAssignment],
        context: AssignmentContext,
    ) -> list[CandidateAssignment]:
        model = cp_model.CpModel()
        variables = {idx: model.NewBoolVar(f"x_{idx}") for idx, _ in enumerate(candidates)}

        runs_to_indices: dict[str, list[int]] = defaultdict(list)
        drivers_to_indices: dict[int, list[int]] = defaultdict(list)
        vehicles_to_indices: dict[int, list[int]] = defaultdict(list)
        for idx, candidate in enumerate(candidates):
            runs_to_indices[candidate.run_id].append(idx)
            drivers_to_indices[candidate.driver_id].append(idx)
            vehicles_to_indices[candidate.vehicle_id].append(idx)

        for indices in runs_to_indices.values():
            model.Add(sum(variables[idx] for idx in indices) <= 1)

        self._add_overlap_constraints(model, variables, candidates, drivers_to_indices, context)
        self._add_overlap_constraints(model, variables, candidates, vehicles_to_indices, context)

        max_driver_minutes = model.NewIntVar(0, 24 * 60, "max_driver_minutes")
        max_driver_runs = model.NewIntVar(0, len(runs_to_indices), "max_driver_runs")
        used_driver_vars: dict[int, "cp_model.IntVar"] = {}
        for driver_id, indices in drivers_to_indices.items():
            total = model.NewIntVar(0, 24 * 60, f"driver_total_{driver_id}")
            model.Add(total == sum(variables[idx] * candidates[idx].work_minutes for idx in indices))
            model.Add(total <= max_driver_minutes)
            run_count = model.NewIntVar(0, len(runs_to_indices), f"driver_run_count_{driver_id}")
            model.Add(run_count == sum(variables[idx] for idx in indices))
            model.Add(run_count <= max_driver_runs)
            used_var = model.NewBoolVar(f"driver_used_{driver_id}")
            used_driver_vars[driver_id] = used_var
            for idx in indices:
                model.Add(variables[idx] <= used_var)
            model.Add(used_var <= sum(variables[idx] for idx in indices))

        urgent_indices = [
            idx for idx, candidate in enumerate(candidates) if context.runs_by_id[candidate.run_id].urgent_count > 0
        ]
        if urgent_indices:
            urgent_expr = sum(variables[idx] for idx in urgent_indices)
            best_urgent_coverage = self._lock_stage_or_none(model, urgent_expr, maximize=True)
            if best_urgent_coverage is None:
                return self._solve_greedily(candidates, context)

        preferred_zone_expr = sum(
            variables[idx] * candidates[idx].preferred_zone_match
            for idx in range(len(candidates))
        )
        best_preferred_zone_matches = self._lock_stage_or_none(model, preferred_zone_expr, maximize=True)
        if best_preferred_zone_matches is None:
            return self._solve_greedily(candidates, context)

        use_zone_vars: dict[tuple[int, object, str], "cp_model.IntVar"] = {}
        grouped_zone_indices: dict[tuple[int, object, str], list[int]] = defaultdict(list)
        driver_day_zone_codes: dict[tuple[int, object], set[str]] = defaultdict(set)
        for idx, candidate in enumerate(candidates):
            run = context.runs_by_id[candidate.run_id]
            dispatch_date = run.dispatch_date
            zone_code = str(run.zone_code)
            key = (candidate.driver_id, dispatch_date, zone_code)
            grouped_zone_indices[key].append(idx)
            driver_day_zone_codes[(candidate.driver_id, dispatch_date)].add(zone_code)

        zone_var_index = 0
        for (driver_id, dispatch_date, zone_code), indices in grouped_zone_indices.items():
            zone_var_index += 1
            use_var = model.NewBoolVar(f"use_zone_{zone_var_index}")
            use_zone_vars[(driver_id, dispatch_date, zone_code)] = use_var
            for idx in indices:
                model.Add(variables[idx] <= use_var)

        zone_spread_proxy_vars: list["cp_model.IntVar"] = []
        for (driver_id, dispatch_date), zone_codes in driver_day_zone_codes.items():
            sorted_zone_codes = sorted(zone_codes)
            distinct_zone_count = model.NewIntVar(
                0,
                len(sorted_zone_codes),
                f"distinct_zone_count_d{driver_id}_{dispatch_date}",
            )
            model.Add(
                distinct_zone_count
                == sum(use_zone_vars[(driver_id, dispatch_date, zone_code)] for zone_code in sorted_zone_codes)
            )
            proxy = model.NewIntVar(
                0,
                max(len(sorted_zone_codes) - 1, 0),
                f"zone_spread_proxy_d{driver_id}_{dispatch_date}",
            )
            model.Add(proxy >= distinct_zone_count - 1)
            zone_spread_proxy_vars.append(proxy)

        if zone_spread_proxy_vars:
            total_zone_spread_proxy = model.NewIntVar(
                0,
                sum(max(len(zone_codes) - 1, 0) for zone_codes in driver_day_zone_codes.values()),
                "total_zone_spread_proxy",
            )
            model.Add(total_zone_spread_proxy == sum(zone_spread_proxy_vars))
            best_zone_spread_proxy = self._lock_stage_or_none(model, total_zone_spread_proxy, maximize=False)
            if best_zone_spread_proxy is None:
                return self._solve_greedily(candidates, context)

        assigned_runs_expr = sum(variables[idx] for idx in range(len(candidates)))
        best_assigned_runs = self._lock_stage_or_none(model, assigned_runs_expr, maximize=True)
        if best_assigned_runs is None:
            return self._solve_greedily(candidates, context)

        use_vehicle_vars: dict[tuple[int, object, int], "cp_model.IntVar"] = {}
        grouped_vehicle_indices: dict[tuple[int, object, int], list[int]] = defaultdict(list)
        driver_day_vehicle_ids: dict[tuple[int, object], set[int]] = defaultdict(set)
        for idx, candidate in enumerate(candidates):
            dispatch_date = context.runs_by_id[candidate.run_id].dispatch_date
            key = (candidate.driver_id, dispatch_date, candidate.vehicle_id)
            grouped_vehicle_indices[key].append(idx)
            driver_day_vehicle_ids[(candidate.driver_id, dispatch_date)].add(candidate.vehicle_id)

        for (driver_id, dispatch_date, vehicle_id), indices in grouped_vehicle_indices.items():
            use_var = model.NewBoolVar(f"use_vehicle_d{driver_id}_{dispatch_date}_v{vehicle_id}")
            use_vehicle_vars[(driver_id, dispatch_date, vehicle_id)] = use_var
            for idx in indices:
                model.Add(variables[idx] <= use_var)

        switch_proxy_vars: list["cp_model.IntVar"] = []
        for (driver_id, dispatch_date), vehicle_ids in driver_day_vehicle_ids.items():
            sorted_vehicle_ids = sorted(vehicle_ids)
            distinct_vehicle_count = model.NewIntVar(
                0,
                len(sorted_vehicle_ids),
                f"distinct_vehicle_count_d{driver_id}_{dispatch_date}",
            )
            model.Add(
                distinct_vehicle_count
                == sum(use_vehicle_vars[(driver_id, dispatch_date, vehicle_id)] for vehicle_id in sorted_vehicle_ids)
            )
            proxy = model.NewIntVar(
                0,
                max(len(sorted_vehicle_ids) - 1, 0),
                f"switch_proxy_d{driver_id}_{dispatch_date}",
            )
            model.Add(proxy >= distinct_vehicle_count - 1)
            switch_proxy_vars.append(proxy)

        if switch_proxy_vars:
            total_switch_proxy = model.NewIntVar(
                0,
                sum(max(len(vehicle_ids) - 1, 0) for vehicle_ids in driver_day_vehicle_ids.values()),
                "total_switch_proxy",
            )
            model.Add(total_switch_proxy == sum(switch_proxy_vars))
            best_total_switch_proxy = self._lock_stage_or_none(model, total_switch_proxy, maximize=False)
            if best_total_switch_proxy is None:
                return self._solve_greedily(candidates, context)

        if used_driver_vars:
            used_driver_expr = sum(used_driver_vars.values())
            best_used_drivers = self._lock_stage_or_none(model, used_driver_expr, maximize=True)
            if best_used_drivers is None:
                return self._solve_greedily(candidates, context)

        best_max_driver_runs = self._lock_stage_or_none(model, max_driver_runs, maximize=False)
        if best_max_driver_runs is None:
            return self._solve_greedily(candidates, context)

        best_max_driver_minutes = self._lock_stage_or_none(model, max_driver_minutes, maximize=False)
        if best_max_driver_minutes is None:
            return self._solve_greedily(candidates, context)

        ordinary_objective_expr = sum(variables[idx] * candidates[idx].objective_score for idx in range(len(candidates)))
        best_ordinary_objective = self._lock_stage_or_none(model, ordinary_objective_expr, maximize=True)
        if best_ordinary_objective is None:
            return self._solve_greedily(candidates, context)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.scoring_policy.cp_sat_time_limit_seconds
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return self._solve_greedily(candidates, context)

        selected = [candidate for idx, candidate in enumerate(candidates) if solver.Value(variables[idx]) == 1]
        return sorted(selected, key=lambda item: (item.estimated_start, -item.objective_score))

    def _solve_greedily(
        self,
        candidates: list[CandidateAssignment],
        context: AssignmentContext,
    ) -> list[CandidateAssignment]:
        by_run: dict[str, list[CandidateAssignment]] = defaultdict(list)
        for candidate in candidates:
            by_run[candidate.run_id].append(candidate)

        current_driver_minutes: dict[int, int] = defaultdict(int)
        selected: list[CandidateAssignment] = []
        driver_intervals: dict[int, list[CandidateAssignment]] = defaultdict(list)
        vehicle_intervals: dict[int, list[CandidateAssignment]] = defaultdict(list)
        selected_by_driver_day: dict[tuple[int, object], list[CandidateAssignment]] = defaultdict(list)
        selected_run_counts: dict[int, int] = defaultdict(int)

        for run_id, options in sorted(
            by_run.items(),
            key=lambda item: (
                0 if context.runs_by_id[item[0]].urgent_count > 0 else 1,
                0 if context.runs_by_id[item[0]].designated_driver_id is not None else 1,
                context.runs_by_id[item[0]].window_start,
                -len(item[1]),
            ),
        ):
            ranked = sorted(
                options,
                key=lambda candidate: self._build_greedy_sort_key(
                    candidate,
                    selected_by_driver_day,
                    selected_run_counts,
                    current_driver_minutes,
                    context,
                ),
            )
            for candidate in ranked:
                if self._has_overlap(driver_intervals[candidate.driver_id], candidate, context):
                    continue
                if self._has_overlap(vehicle_intervals[candidate.vehicle_id], candidate, context):
                    continue
                selected.append(candidate)
                driver_intervals[candidate.driver_id].append(candidate)
                vehicle_intervals[candidate.vehicle_id].append(candidate)
                dispatch_date = context.runs_by_id[candidate.run_id].dispatch_date
                selected_by_driver_day[(candidate.driver_id, dispatch_date)].append(candidate)
                current_driver_minutes[candidate.driver_id] += candidate.work_minutes
                selected_run_counts[candidate.driver_id] += 1
                break
        return sorted(selected, key=lambda item: (item.estimated_start, -item.objective_score))

    def _build_greedy_sort_key(
        self,
        candidate: CandidateAssignment,
        selected_by_driver_day: dict[tuple[int, object], list[CandidateAssignment]],
        selected_run_counts: dict[int, int],
        current_driver_minutes: dict[int, int],
        context: AssignmentContext,
    ) -> tuple[int, int, int, int, int, int, int, int, int, str, int]:
        driver_id = candidate.driver_id
        driver_run_count = selected_run_counts[driver_id]
        driver_minutes = current_driver_minutes[driver_id]
        return (
            0 if candidate.preferred_zone_match else 1,
            0 if self._same_zone_continuity_hit(candidate, selected_by_driver_day, context) else 1,
            self._zone_mismatch_rank(candidate, context),
            -(
                candidate.objective_score
                - self._switch_delta_penalty_for_candidate(candidate, selected_by_driver_day, context)
                + (self.scoring_policy.unused_driver_bonus if driver_run_count == 0 else 0)
                - driver_run_count * self.scoring_policy.driver_run_balance_weight
                - driver_minutes * self.scoring_policy.driver_balance_penalty_per_min
            ),
            self._switch_delta_for_candidate(candidate, selected_by_driver_day, context),
            0 if driver_run_count == 0 else 1,
            driver_run_count,
            driver_minutes,
            candidate.estimated_finish,
            candidate.run_id,
            candidate.vehicle_id,
        )

    @staticmethod
    def _add_overlap_constraints(
        model: "cp_model.CpModel",
        variables: dict[int, "cp_model.IntVar"],
        candidates: list[CandidateAssignment],
        grouped_indices: dict[int, list[int]],
        context: AssignmentContext,
    ) -> None:
        for indices in grouped_indices.values():
            for left_pos, left_idx in enumerate(indices):
                left_candidate = candidates[left_idx]
                for right_idx in indices[left_pos + 1 :]:
                    right_candidate = candidates[right_idx]
                    if AssignmentSolver._intervals_overlap(left_candidate, right_candidate, context):
                        model.Add(variables[left_idx] + variables[right_idx] <= 1)

    @staticmethod
    def _has_overlap(
        intervals: list[CandidateAssignment],
        candidate: CandidateAssignment,
        context: AssignmentContext,
    ) -> bool:
        return any(
            AssignmentSolver._intervals_overlap(existing, candidate, context)
            for existing in intervals
        )

    @staticmethod
    def _intervals_overlap(left: CandidateAssignment, right: CandidateAssignment, context: AssignmentContext) -> bool:
        left_date = context.runs_by_id[left.run_id].dispatch_date
        right_date = context.runs_by_id[right.run_id].dispatch_date
        if left_date != right_date:
            return False
        return left.estimated_start < right.estimated_finish and right.estimated_start < left.estimated_finish

    def _switch_delta_penalty_for_candidate(
        self,
        candidate: CandidateAssignment,
        selected_by_driver_day: dict[tuple[int, object], list[CandidateAssignment]],
        context: AssignmentContext,
    ) -> int:
        delta_switches = self._switch_delta_for_candidate(candidate, selected_by_driver_day, context)
        return delta_switches * self.scoring_policy.vehicle_switch_penalty

    def _switch_delta_for_candidate(
        self,
        candidate: CandidateAssignment,
        selected_by_driver_day: dict[tuple[int, object], list[CandidateAssignment]],
        context: AssignmentContext,
    ) -> int:
        dispatch_date = context.runs_by_id[candidate.run_id].dispatch_date
        key = (candidate.driver_id, dispatch_date)
        existing = selected_by_driver_day.get(key, [])
        return self._delta_switches_after_insertion(existing, candidate)

    def _same_zone_continuity_hit(
        self,
        candidate: CandidateAssignment,
        selected_by_driver_day: dict[tuple[int, object], list[CandidateAssignment]],
        context: AssignmentContext,
    ) -> bool:
        run = context.runs_by_id[candidate.run_id]
        key = (candidate.driver_id, run.dispatch_date)
        existing = selected_by_driver_day.get(key, [])
        if not existing:
            return False
        return any(context.runs_by_id[item.run_id].zone_code == run.zone_code for item in existing)

    def _zone_mismatch_rank(
        self,
        candidate: CandidateAssignment,
        context: AssignmentContext,
    ) -> int:
        driver = context.drivers_by_id[candidate.driver_id]
        if not driver.preferred_zone_codes:
            return 0
        return 0 if candidate.preferred_zone_match else 1

    @staticmethod
    def _delta_switches_after_insertion(
        existing: list[CandidateAssignment],
        candidate: CandidateAssignment,
    ) -> int:
        before = AssignmentSolver._count_vehicle_switches(existing)
        after = AssignmentSolver._count_vehicle_switches([*existing, candidate])
        return max(after - before, 0)

    @staticmethod
    def _count_vehicle_switches(items: list[CandidateAssignment]) -> int:
        if len(items) <= 1:
            return 0
        ordered = sorted(
            items,
            key=lambda item: (item.estimated_start, item.estimated_finish, item.run_id),
        )
        switches = 0
        for index in range(1, len(ordered)):
            if ordered[index - 1].vehicle_id != ordered[index].vehicle_id:
                switches += 1
        return switches

    def _annotate_vehicle_switch_explanations(
        self,
        selected: list[CandidateAssignment],
        all_candidates: list[CandidateAssignment],
        context: AssignmentContext,
    ) -> list[CandidateAssignment]:
        if not selected:
            return selected

        candidates_by_run_driver: dict[tuple[str, int], list[CandidateAssignment]] = defaultdict(list)
        for candidate in all_candidates:
            candidates_by_run_driver[(candidate.run_id, candidate.driver_id)].append(candidate)

        selected_by_driver_day: dict[tuple[int, object], list[CandidateAssignment]] = defaultdict(list)
        for candidate in selected:
            dispatch_date = context.runs_by_id[candidate.run_id].dispatch_date
            selected_by_driver_day[(candidate.driver_id, dispatch_date)].append(candidate)

        extra_by_run_id: dict[str, list[str]] = defaultdict(list)
        for (driver_id, dispatch_date), sequence in selected_by_driver_day.items():
            ordered = sorted(sequence, key=lambda item: (item.estimated_start, item.estimated_finish, item.run_id))
            for index in range(1, len(ordered)):
                previous = ordered[index - 1]
                current = ordered[index]
                if previous.vehicle_id == current.vehicle_id:
                    extra_by_run_id[current.run_id].append("Kept same vehicle across consecutive runs for this driver.")
                    continue

                extra_by_run_id[current.run_id].append("Vehicle switch applied between consecutive runs for this driver.")
                same_vehicle_options = [
                    option
                    for option in candidates_by_run_driver.get((current.run_id, driver_id), [])
                    if option.vehicle_id == previous.vehicle_id
                ]
                if self._switch_forced_by_feasibility_or_resources(
                    current,
                    same_vehicle_options,
                    selected,
                    context,
                ):
                    extra_by_run_id[current.run_id].append("Switched vehicle due to feasibility/resource constraints.")

        annotated: list[CandidateAssignment] = []
        for candidate in selected:
            extra_messages = extra_by_run_id.get(candidate.run_id, [])
            annotated.append(self._append_explanation_messages(candidate, extra_messages))
        return annotated

    def _annotate_driver_utilization_explanations(
        self,
        selected: list[CandidateAssignment],
        context: AssignmentContext,
    ) -> list[CandidateAssignment]:
        if not selected:
            return selected

        used_driver_day: set[tuple[int, object]] = set()
        ordered = sorted(selected, key=lambda item: (context.runs_by_id[item.run_id].dispatch_date, item.estimated_start, item.run_id))
        annotated: list[CandidateAssignment] = []
        for candidate in ordered:
            extra_messages = self._build_driver_utilization_messages(candidate, used_driver_day, context)
            annotated.append(self._append_explanation_messages(candidate, extra_messages))
        return annotated

    @staticmethod
    def _append_explanation_messages(
        candidate: CandidateAssignment,
        extra_messages: list[str],
    ) -> CandidateAssignment:
        if not extra_messages:
            return candidate
        deduplicated = tuple(dict.fromkeys(extra_messages))
        return replace(candidate, explanation=candidate.explanation + deduplicated)

    def _build_driver_utilization_messages(
        self,
        candidate: CandidateAssignment,
        used_driver_day: set[tuple[int, object]],
        context: AssignmentContext,
    ) -> list[str]:
        run = context.runs_by_id[candidate.run_id]
        dispatch_key = (candidate.driver_id, run.dispatch_date)
        extra_messages: list[str] = []
        if dispatch_key not in used_driver_day:
            extra_messages.append("Selected to improve driver utilization on this dispatch date.")
            used_driver_day.add(dispatch_key)
        if run.urgent_count > 0:
            extra_messages.append("Selected due to urgent coverage priority.")
        if run.designated_driver_id is not None:
            extra_messages.append("Selected due to designated driver requirement.")
        return extra_messages

    def _switch_forced_by_feasibility_or_resources(
        self,
        selected_candidate: CandidateAssignment,
        same_vehicle_options: list[CandidateAssignment],
        final_selected: list[CandidateAssignment],
        context: AssignmentContext,
    ) -> bool:
        if not same_vehicle_options:
            return True

        baseline = [candidate for candidate in final_selected if candidate.run_id != selected_candidate.run_id]
        for option in same_vehicle_options:
            if self._candidate_fits_selected_resources(option, baseline, context):
                return False
        return True

    @staticmethod
    def _candidate_fits_selected_resources(
        candidate: CandidateAssignment,
        baseline: list[CandidateAssignment],
        context: AssignmentContext,
    ) -> bool:
        for existing in baseline:
            if existing.driver_id == candidate.driver_id and AssignmentSolver._intervals_overlap(existing, candidate, context):
                return False
            if existing.vehicle_id == candidate.vehicle_id and AssignmentSolver._intervals_overlap(existing, candidate, context):
                return False
        return True
