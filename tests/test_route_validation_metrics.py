from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from dispatch_optimizer.assignment_core import CandidateEnumerator
from dispatch_optimizer.models import (
    DispatchDriver,
    DispatchOrder,
    DispatchRun,
    DispatchVehicle,
    LoadType,
    LoadVector,
    Urgency,
)
from dispatch_optimizer.routing_core import (
    DEFAULT_CANDIDATE_ROUTE_TIME_LIMIT_SECONDS,
    RoutePlanner,
    RouteResult,
)


class _FixedTravelProvider:
    def travel_minutes(self, origin, destination) -> int:
        return 5


def _order(order_id: int = 1001) -> DispatchOrder:
    return DispatchOrder(
        order_id=order_id,
        dispatch_date=date(2026, 5, 4),
        delivery_address="Order Address",
        lat=-37.80,
        lng=144.95,
        zone_code="LOCAL",
        urgency=Urgency.NORMAL,
        window_start=8 * 60,
        window_end=12 * 60,
        load_type=LoadType.MIXED,
        kg_count=10.0,
        pallet_count=1,
        bag_count=0,
        postcode="3000",
        suburb="Melbourne",
        metadata={},
    )


def _driver(driver_id: int = 1) -> DispatchDriver:
    return DispatchDriver(
        driver_id=driver_id,
        shift_start=7 * 60,
        shift_end=17 * 60,
        is_available=True,
        start_location="Depot",
        end_location="Depot",
        preferred_zone_codes=("LOCAL",),
        historical_vehicle_ids=(101,),
        start_lat=-37.81,
        start_lng=144.96,
        end_lat=-37.81,
        end_lng=144.96,
        metadata={},
    )


def _vehicle(vehicle_id: int = 101) -> DispatchVehicle:
    return DispatchVehicle(
        vehicle_id=vehicle_id,
        vehicle_type="Van",
        is_available=True,
        kg_capacity=1000.0,
        pallet_capacity=10,
        tub_capacity=20,
        trolley_capacity=0,
        stillage_capacity=0,
        loose_capacity=80,
        metadata={},
    )


def _run(order: DispatchOrder | None = None) -> DispatchRun:
    selected_order = order or _order()
    return DispatchRun(
        run_id="RUN-0001",
        dispatch_date=selected_order.dispatch_date,
        zone_code=selected_order.zone_code or "LOCAL",
        bucket_start=8 * 60,
        bucket_end=10 * 60,
        orders=[selected_order],
        load=LoadVector(kg=selected_order.kg_count, pallets=selected_order.pallet_count),
        estimated_service_minutes=20,
    )


class RoutePlannerMetricsTest(unittest.TestCase):
    def test_route_planner_default_candidate_time_limit_seconds(self) -> None:
        planner = RoutePlanner(_FixedTravelProvider())
        self.assertEqual(DEFAULT_CANDIDATE_ROUTE_TIME_LIMIT_SECONDS, planner.candidate_route_time_limit_seconds)

    def test_route_planner_candidate_time_limit_override_supported(self) -> None:
        planner = RoutePlanner(_FixedTravelProvider(), candidate_route_time_limit_seconds=2.0)
        self.assertEqual(2.0, planner.candidate_route_time_limit_seconds)

    def test_route_planner_applies_fractional_time_limit_without_truncation(self) -> None:
        planner = RoutePlanner(_FixedTravelProvider(), candidate_route_time_limit_seconds=0.25)

        class _Duration:
            def __init__(self) -> None:
                self.seconds = -1
                self.nanos = -1

        class _SearchParameters:
            def __init__(self) -> None:
                self.time_limit = _Duration()

        parameters = _SearchParameters()
        planner._apply_candidate_route_time_limit(parameters)
        self.assertEqual(0, parameters.time_limit.seconds)
        self.assertEqual(250_000_000, parameters.time_limit.nanos)

    def test_route_planner_metrics_track_calls_cache_and_total_ms(self) -> None:
        planner = RoutePlanner(_FixedTravelProvider())
        driver = _driver()
        vehicle = _vehicle()
        run = _run()

        planner.reset_metrics()
        with patch("dispatch_optimizer.routing_core.ORTOOLS_ROUTING_AVAILABLE", False):
            planner.plan(run, driver, vehicle)
            planner.plan(run, driver, vehicle)

        metrics = planner.metrics_snapshot()
        self.assertEqual(2, metrics["route_plan_calls"])
        self.assertEqual(1, metrics["route_cache_hits"])
        self.assertEqual(1, metrics["route_cache_misses"])
        self.assertGreaterEqual(metrics["route_plan_total_ms"], 0.0)
        self.assertEqual(1, planner.cache_hits)
        self.assertEqual(1, planner.cache_misses)

    def test_route_planner_timeout_count_is_strict_status_only(self) -> None:
        planner = RoutePlanner(_FixedTravelProvider())
        planner.reset_metrics()

        timeout_status = planner._routing_fail_timeout_status()
        planner._record_route_timeout_status(None)
        planner._record_route_timeout_status(99999)
        if timeout_status is not None:
            planner._record_route_timeout_status(timeout_status)
            self.assertEqual(1, planner.metrics_snapshot()["route_plan_timeout_count"])
        else:
            self.assertEqual(0, planner.metrics_snapshot()["route_plan_timeout_count"])

    def test_route_planner_reset_metrics_clears_snapshot(self) -> None:
        planner = RoutePlanner(_FixedTravelProvider())
        planner.route_plan_calls = 3
        planner.route_cache_hits = 2
        planner.route_cache_misses = 1
        planner.route_plan_total_ms = 123.4
        planner.route_plan_timeout_count = 1

        planner.reset_metrics()
        self.assertEqual(
            {
                "route_plan_calls": 0,
                "route_cache_hits": 0,
                "route_cache_misses": 0,
                "route_plan_total_ms": 0.0,
                "route_plan_timeout_count": 0,
            },
            planner.metrics_snapshot(),
        )


class CandidateEnumeratorMetricsTest(unittest.TestCase):
    def test_candidate_metrics_count_candidates_without_route_validation(self) -> None:
        enumerator = CandidateEnumerator(route_planner=None)
        enumerator.reset_metrics()

        candidates, rejected_runs = enumerator.enumerate([_run()], [_driver()], [_vehicle()])

        self.assertEqual([], rejected_runs)
        self.assertEqual(1, len(candidates))
        metrics = enumerator.metrics_snapshot()
        self.assertEqual(len(candidates), metrics["candidate_count"])
        self.assertEqual(0, metrics["validated_candidate_count"])

    def test_candidate_metrics_count_validated_candidates(self) -> None:
        class _AlwaysFeasiblePlanner:
            def plan(self, run, driver, vehicle):
                return RouteResult(
                    feasible=True,
                    ordered_orders=tuple(run.orders),
                    planned_start=max(driver.shift_start, run.window_start),
                    planned_finish=max(driver.shift_start, run.window_start) + run.estimated_service_minutes,
                    travel_minutes=15,
                    deadhead_minutes=5,
                    stop_plans=(),
                )

        enumerator = CandidateEnumerator(route_planner=_AlwaysFeasiblePlanner())
        enumerator.reset_metrics()
        with patch.object(enumerator, "_needs_route_validation", return_value=True):
            candidates, rejected_runs = enumerator.enumerate([_run()], [_driver()], [_vehicle()])

        self.assertEqual([], rejected_runs)
        self.assertEqual(1, len(candidates))
        self.assertIn(
            "Validated with route-level feasibility check for high-priority/boundary candidate.",
            candidates[0].explanation,
        )
        metrics = enumerator.metrics_snapshot()
        self.assertEqual(1, metrics["candidate_count"])
        self.assertEqual(1, metrics["validated_candidate_count"])

    def test_candidate_metrics_reset_clears_snapshot(self) -> None:
        enumerator = CandidateEnumerator(route_planner=None)
        enumerator.candidate_count = 11
        enumerator.validated_candidate_count = 4
        enumerator.reset_metrics()

        self.assertEqual(
            {"candidate_count": 0, "validated_candidate_count": 0},
            enumerator.metrics_snapshot(),
        )
