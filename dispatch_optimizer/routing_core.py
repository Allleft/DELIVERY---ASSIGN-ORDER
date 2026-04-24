from __future__ import annotations

from dataclasses import dataclass

from .models import (
    FIXED_STOP_MINUTES,
    CandidateAssignment,
    DispatchDriver,
    DispatchOrder,
    DispatchPlan,
    DispatchRun,
    DispatchStopPlan,
    DispatchVehicle,
    LocationRef,
    minutes_to_hhmm,
)
from .providers import TravelTimeProvider

try:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    ORTOOLS_ROUTING_AVAILABLE = True
except ModuleNotFoundError:
    ORTOOLS_ROUTING_AVAILABLE = False


@dataclass(frozen=True)
class RouteResult:
    feasible: bool
    ordered_orders: tuple[DispatchOrder, ...]
    planned_start: int
    planned_finish: int
    travel_minutes: int
    deadhead_minutes: int
    stop_plans: tuple[DispatchStopPlan, ...]
    reason_code: str | None = None
    reason_text: str | None = None


class RoutePlanner:
    def __init__(self, travel_provider: TravelTimeProvider):
        self.travel_provider = travel_provider
        self._route_cache: dict[tuple, RouteResult] = {}
        self.cache_hits = 0
        self.cache_misses = 0

    def plan(self, run: DispatchRun, driver: DispatchDriver, vehicle: DispatchVehicle, objective_score: int = 0) -> RouteResult:
        cache_key = self._route_cache_key(run, driver, vehicle)
        cached = self._route_cache.get(cache_key)
        if cached is not None:
            self.cache_hits += 1
            return cached
        self.cache_misses += 1
        self._prefetch_run_pairs(run, driver)
        if ORTOOLS_ROUTING_AVAILABLE:
            result = self._plan_with_ortools(run, driver)
            if result.feasible:
                self._route_cache[cache_key] = result
                return result
        result = self._plan_greedily(run, driver)
        self._route_cache[cache_key] = result
        return result

    def build_dispatch_plan(
        self,
        run: DispatchRun,
        driver: DispatchDriver,
        vehicle: DispatchVehicle,
        candidate: CandidateAssignment,
    ) -> DispatchPlan:
        route = self.plan(run, driver, vehicle, objective_score=candidate.objective_score)
        return self.build_dispatch_plan_from_route(run, driver, vehicle, candidate, route)

    def build_dispatch_plan_from_route(
        self,
        run: DispatchRun,
        driver: DispatchDriver,
        vehicle: DispatchVehicle,
        candidate: CandidateAssignment,
        route: RouteResult,
    ) -> DispatchPlan:
        if not route.feasible:
            raise ValueError("Cannot build dispatch plan from infeasible route.")
        return DispatchPlan(
            plan_id=run.run_id.replace("RUN-", "PLAN-", 1) if run.run_id.startswith("RUN-") else f"PLAN-{run.run_id}",
            dispatch_date=run.dispatch_date,
            driver_id=driver.driver_id,
            vehicle_id=vehicle.vehicle_id,
            order_ids=tuple(order.order_id for order in run.orders),
            total_orders=len(run.orders),
            load_summary=run.load.as_dict(),
            zone_code=run.zone_code,
            time_window_start=run.window_start,
            time_window_end=run.window_end,
            urgent_order_count=run.urgent_count,
            objective_score=candidate.objective_score,
            explanation=candidate.explanation
            + (
                f"Route planned from {driver.start_location} to {driver.end_location}.",
                f"Estimated deadhead {route.deadhead_minutes} min and line-haul {route.travel_minutes} min.",
            ),
            stop_sequence=route.stop_plans,
            planned_start=route.planned_start,
            planned_finish=route.planned_finish,
            etas={stop.order_id: minutes_to_hhmm(stop.eta) for stop in route.stop_plans},
        )

    @staticmethod
    def _route_cache_key(run: DispatchRun, driver: DispatchDriver, vehicle: DispatchVehicle) -> tuple:
        order_signature = tuple(
            sorted(
                (
                    order.order_id,
                    order.window_start,
                    order.window_end,
                    FIXED_STOP_MINUTES,
                )
                for order in run.orders
            )
        )
        return run.run_id, driver.driver_id, vehicle.vehicle_id, order_signature

    def _prefetch_run_pairs(self, run: DispatchRun, driver: DispatchDriver) -> None:
        prefetch = getattr(self.travel_provider, "prefetch_pairs", None)
        if not callable(prefetch):
            return
        if driver.start_ref is None or driver.end_ref is None:
            return
        order_locations = [order.location for order in run.orders if order.location is not None]
        if len(order_locations) != len(run.orders):
            return

        start_ref = driver.start_ref
        end_ref = driver.end_ref
        pairs: list[tuple[LocationRef, LocationRef]] = [(start_ref, end_ref)]
        for location in order_locations:
            pairs.append((start_ref, location))
            pairs.append((location, end_ref))
        for source in order_locations:
            for target in order_locations:
                if source == target:
                    continue
                pairs.append((source, target))
        try:
            prefetch(pairs)
        except Exception:
            # Prefetch is opportunistic; routing will degrade to per-leg lookups.
            return

    def _plan_greedily(self, run: DispatchRun, driver: DispatchDriver) -> RouteResult:
        if driver.start_ref is None or driver.end_ref is None:
            return RouteResult(
                feasible=False,
                ordered_orders=(),
                planned_start=driver.shift_start,
                planned_finish=driver.shift_start,
                travel_minutes=0,
                deadhead_minutes=0,
                stop_plans=(),
                reason_code="MISSING_DRIVER_COORDS",
                reason_text="Driver coordinates are missing.",
            )

        remaining = list(run.orders)
        current_location = driver.start_ref
        current_time = max(driver.shift_start, run.window_start)
        stop_plans: list[DispatchStopPlan] = []
        total_travel = 0
        ordered_orders: list[DispatchOrder] = []
        deadhead_minutes = 0

        while remaining:
            candidates: list[tuple[int, int, DispatchOrder, int]] = []
            for order in remaining:
                order_ref = order.location
                if order_ref is None:
                    continue
                travel = self.travel_provider.travel_minutes(current_location, order_ref)
                arrival = current_time + travel
                eta = max(arrival, order.window_start)
                if eta > order.window_end:
                    continue
                slack = order.window_end - eta
                candidates.append((slack, travel, order, eta))

            if not candidates:
                return RouteResult(
                    feasible=False,
                    ordered_orders=tuple(ordered_orders),
                    planned_start=max(driver.shift_start, run.window_start),
                    planned_finish=current_time,
                    travel_minutes=total_travel,
                    deadhead_minutes=deadhead_minutes,
                    stop_plans=tuple(stop_plans),
                    reason_code="TIME_WINDOW_INFEASIBLE",
                    reason_text="No feasible next stop satisfies the remaining time windows.",
                )

            candidates.sort(
                key=lambda item: (
                    item[0],
                    item[1],
                    0 if item[2].urgency.value == "URGENT" else 1,
                    item[2].window_end,
                )
            )
            _, travel, chosen_order, eta = candidates[0]
            if not ordered_orders:
                deadhead_minutes = travel
            total_travel += travel
            departure = eta + FIXED_STOP_MINUTES
            stop_plans.append(
                DispatchStopPlan(
                    order_id=chosen_order.order_id,
                    sequence=len(stop_plans) + 1,
                    eta=eta,
                    departure=departure,
                    travel_from_previous=travel,
                )
            )
            ordered_orders.append(chosen_order)
            remaining.remove(chosen_order)
            current_time = departure
            current_location = chosen_order.location

        end_leg = self.travel_provider.travel_minutes(current_location, driver.end_ref)
        planned_finish = current_time + end_leg
        total_travel += end_leg
        if planned_finish > driver.shift_end:
            return RouteResult(
                feasible=False,
                ordered_orders=tuple(ordered_orders),
                planned_start=max(driver.shift_start, run.window_start),
                planned_finish=planned_finish,
                travel_minutes=total_travel,
                deadhead_minutes=deadhead_minutes,
                stop_plans=tuple(stop_plans),
                reason_code="SHIFT_OVERRUN",
                reason_text="Route finishes after driver shift end.",
            )

        return RouteResult(
            feasible=True,
            ordered_orders=tuple(ordered_orders),
            planned_start=max(driver.shift_start, run.window_start),
            planned_finish=planned_finish,
            travel_minutes=total_travel,
            deadhead_minutes=deadhead_minutes,
            stop_plans=tuple(stop_plans),
        )

    def _plan_with_ortools(self, run: DispatchRun, driver: DispatchDriver) -> RouteResult:
        if driver.start_ref is None or driver.end_ref is None:
            return RouteResult(
                feasible=False,
                ordered_orders=(),
                planned_start=driver.shift_start,
                planned_finish=driver.shift_start,
                travel_minutes=0,
                deadhead_minutes=0,
                stop_plans=(),
                reason_code="MISSING_DRIVER_COORDS",
                reason_text="Driver coordinates are missing.",
            )

        orders = [order for order in run.orders if order.location is not None]
        if len(orders) != len(run.orders):
            return RouteResult(
                feasible=False,
                ordered_orders=(),
                planned_start=driver.shift_start,
                planned_finish=driver.shift_start,
                travel_minutes=0,
                deadhead_minutes=0,
                stop_plans=(),
                reason_code="MISSING_ORDER_COORDS",
                reason_text="At least one order is missing coordinates.",
            )

        locations: list[LocationRef] = [driver.start_ref] + [order.location for order in orders] + [driver.end_ref]
        manager = pywrapcp.RoutingIndexManager(len(locations), 1, [0], [len(locations) - 1])
        routing = pywrapcp.RoutingModel(manager)

        def time_callback(from_index: int, to_index: int) -> int:
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            travel = self.travel_provider.travel_minutes(locations[from_node], locations[to_node])
            service = 0
            if 0 < from_node < len(locations) - 1:
                service = FIXED_STOP_MINUTES
            return travel + service

        transit_callback_index = routing.RegisterTransitCallback(time_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
        routing.AddDimension(transit_callback_index, 240, driver.shift_end + 240, False, "Time")
        time_dimension = routing.GetDimensionOrDie("Time")

        time_dimension.CumulVar(routing.Start(0)).SetRange(driver.shift_start, max(driver.shift_start, run.window_start))
        time_dimension.CumulVar(routing.End(0)).SetRange(driver.shift_start, driver.shift_end)

        for idx, order in enumerate(orders, start=1):
            node_index = manager.NodeToIndex(idx)
            time_dimension.CumulVar(node_index).SetRange(order.window_start, order.window_end)

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        search_parameters.time_limit.seconds = 2

        solution = routing.SolveWithParameters(search_parameters)
        if solution is None:
            return self._plan_greedily(run, driver)

        ordered_orders: list[DispatchOrder] = []
        stop_plans: list[DispatchStopPlan] = []
        travel_minutes = 0
        deadhead_minutes = 0
        index = routing.Start(0)
        planned_start = solution.Min(time_dimension.CumulVar(index))
        current_time = planned_start
        sequence = 1
        while not routing.IsEnd(index):
            next_index = solution.Value(routing.NextVar(index))
            from_node = manager.IndexToNode(index)
            to_node = manager.IndexToNode(next_index)
            if 0 < to_node < len(locations) - 1:
                order = orders[to_node - 1]
                leg = self.travel_provider.travel_minutes(locations[from_node], locations[to_node])
                eta = max(current_time + leg, order.window_start)
                if not ordered_orders:
                    deadhead_minutes = leg
                departure = eta + FIXED_STOP_MINUTES
                travel_minutes += leg
                stop_plans.append(
                    DispatchStopPlan(
                        order_id=order.order_id,
                        sequence=sequence,
                        eta=eta,
                        departure=departure,
                        travel_from_previous=leg,
                    )
                )
                ordered_orders.append(order)
                current_time = departure
                sequence += 1
            index = next_index

        if ordered_orders:
            last_ref = ordered_orders[-1].location
            if last_ref is not None:
                travel_minutes += self.travel_provider.travel_minutes(last_ref, driver.end_ref)
        planned_finish = solution.Min(time_dimension.CumulVar(routing.End(0)))
        return RouteResult(
            feasible=planned_finish <= driver.shift_end,
            ordered_orders=tuple(ordered_orders),
            planned_start=planned_start,
            planned_finish=planned_finish,
            travel_minutes=travel_minutes,
            deadhead_minutes=deadhead_minutes,
            stop_plans=tuple(stop_plans),
            reason_code=None if planned_finish <= driver.shift_end else "SHIFT_OVERRUN",
            reason_text=None if planned_finish <= driver.shift_end else "Route finishes after driver shift end.",
        )
