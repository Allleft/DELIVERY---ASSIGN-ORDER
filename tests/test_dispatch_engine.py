from __future__ import annotations

import json
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from dispatch_optimizer.assignment import AssignmentContext, AssignmentSolver, ORTOOLS_CP_SAT_AVAILABLE, ScoringPolicy
from dispatch_optimizer.cli import (
    build_drivers,
    build_drivers_with_legacy,
    build_orders,
    build_vehicles,
    serialize_result,
)
from dispatch_optimizer.engine import DispatchEngine
from dispatch_optimizer.models import (
    CandidateAssignment,
    DispatchDriver,
    DispatchOrderAssignment,
    DispatchOrder,
    DispatchPlan,
    DispatchRun,
    DispatchVehicle,
    FIXED_STOP_MINUTES,
    LoadType,
    LoadVector,
    Urgency,
)
from dispatch_optimizer.providers import DictTravelTimeProvider, StaticGeocoder


DISPATCH_DATE = date(2026, 4, 20)


class DispatchEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.travel_provider = DictTravelTimeProvider(
            {
                ("Depot", "Alpha"): 10,
                ("Depot", "Bravo"): 12,
                ("Alpha", "Bravo"): 10,
                ("Bravo", "Depot"): 10,
                ("Alpha", "Depot"): 10,
                ("Depot", "Heavy"): 20,
                ("Heavy", "Depot"): 20,
                ("Depot", "Near"): 10,
                ("Near", "Depot"): 10,
                ("Depot", "Far"): 15,
                ("Far", "Depot"): 15,
                ("Near", "Far"): 80,
                ("Far", "Near"): 80,
                ("Depot", "Loose"): 8,
                ("Loose", "Depot"): 8,
            },
            default_minutes=20,
        )
        self.engine = DispatchEngine(travel_provider=self.travel_provider, zone_by_postcode={"3000": "LOCAL"})

    def test_prefers_zone_and_historical_vehicle_when_all_else_equal(self) -> None:
        orders = [
            self._order(1, "Alpha", "08:00", "12:00", pallet_count=1),
            self._order(2, "Bravo", "08:00", "12:00", pallet_count=2),
        ]
        drivers = [
            self._driver(1, preferred_zone_codes=("LOCAL",), historical_vehicle_ids=(100,)),
            self._driver(2, is_available=False),
        ]
        vehicles = [
            self._vehicle(100, pallet_capacity=4, tub_capacity=8),
            self._vehicle(200, pallet_capacity=8, tub_capacity=12),
        ]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)

        self.assertEqual(1, len(result.plans))
        self.assertEqual(1, result.plans[0].driver_id)
        self.assertEqual(100, result.plans[0].vehicle_id)
        self.assertFalse(any(exc.reason_code == "RUN_UNASSIGNED" for exc in result.exceptions))

    def test_zone_preference_prioritizes_local_and_west_drivers(self) -> None:
        orders = [
            self._order(901, "Alpha", "08:00", "09:30", pallet_count=1, postcode=None, zone_code="LOCAL"),
            self._order(902, "Bravo", "10:00", "11:30", pallet_count=1, postcode=None, zone_code="WEST"),
        ]
        drivers = [
            self._driver(1, preferred_zone_codes=("LOCAL",)),
            self._driver(2, preferred_zone_codes=("WEST",)),
        ]
        vehicles = [
            self._vehicle(901, pallet_capacity=4, tub_capacity=8),
            self._vehicle(902, pallet_capacity=4, tub_capacity=8),
        ]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)

        self.assertEqual(2, len(result.order_assignments))
        by_order = {item.order_id: item for item in result.order_assignments}
        self.assertEqual(1, by_order[901].driver_id)
        self.assertEqual(2, by_order[902].driver_id)

    def test_cross_zone_assignment_allowed_when_no_matching_preference_driver(self) -> None:
        orders = [self._order(903, "Alpha", "08:00", "11:00", pallet_count=1, postcode=None, zone_code="WEST")]
        drivers = [self._driver(1, preferred_zone_codes=("LOCAL",))]
        vehicles = [self._vehicle(903, pallet_capacity=4, tub_capacity=8)]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)

        self.assertEqual(1, len(result.order_assignments))
        self.assertEqual(1, result.order_assignments[0].driver_id)

    def test_designated_driver_unavailable_returns_exception(self) -> None:
        orders = [self._order(3, "Alpha", "08:00", "10:00", designated_driver_id=99)]
        drivers = [self._driver(1)]
        vehicles = [self._vehicle(100, pallet_capacity=4)]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)

        self.assertEqual(0, len(result.plans))
        self.assertTrue(any(exc.reason_code == "DESIGNATED_DRIVER_UNAVAILABLE" for exc in result.exceptions))

    def test_selects_smallest_feasible_vehicle_at_capacity_boundary(self) -> None:
        orders = [self._order(4, "Heavy", "08:00", "11:00", pallet_count=5)]
        drivers = [self._driver(1)]
        vehicles = [
            self._vehicle(101, pallet_capacity=3, tub_capacity=4),
            self._vehicle(102, pallet_capacity=6, tub_capacity=6),
            self._vehicle(103, pallet_capacity=10, tub_capacity=10),
        ]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)

        self.assertEqual(1, len(result.plans))
        self.assertEqual(102, result.plans[0].vehicle_id)

    def test_repair_splits_infeasible_run_into_two_runs(self) -> None:
        orders = [
            self._order(5, "Near", "09:00", "10:00", pallet_count=1),
            self._order(6, "Far", "09:00", "10:00", pallet_count=1),
        ]
        drivers = [self._driver(1), self._driver(2)]
        vehicles = [
            self._vehicle(201, pallet_capacity=4, tub_capacity=4),
            self._vehicle(202, pallet_capacity=4, tub_capacity=4),
        ]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)

        self.assertGreaterEqual(len(result.plans), 1)
        assigned_order_ids = {order_id for plan in result.plans for order_id in plan.order_ids}
        self.assertTrue(assigned_order_ids.issubset({5, 6}))
        self.assertGreaterEqual(len(assigned_order_ids), 1)

    def test_loose_load_uses_derived_loose_capacity(self) -> None:
        orders = [self._order(7, "Loose", "08:00", "11:00", load_type=LoadType.LOOSE, bag_count=17)]
        drivers = [self._driver(1)]
        vehicles = [
            self._vehicle(301, pallet_capacity=1, tub_capacity=4),
            self._vehicle(302, pallet_capacity=1, tub_capacity=5),
        ]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)

        self.assertEqual(1, len(result.plans))
        self.assertEqual(302, result.plans[0].vehicle_id)

    def test_zero_kg_capacity_does_not_block_other_capacity_dimensions(self) -> None:
        orders = [self._order(8, "Alpha", "08:00", "11:00", pallet_count=2, kg_count=250)]
        drivers = [self._driver(1)]
        vehicles = [self._vehicle(401, pallet_capacity=3, tub_capacity=6, kg_capacity=0)]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)

        self.assertEqual(1, len(result.plans))
        self.assertEqual(0, len(result.exceptions))

    def test_example_snapshot_uses_vehicle_master_export_shape(self) -> None:
        raw = json.loads(Path("examples/sample-dispatch-input.json").read_text(encoding="utf-8"))
        engine = DispatchEngine(
            travel_provider=self.travel_provider,
            zone_by_postcode=raw["zone_by_postcode"],
            geocoder=StaticGeocoder(raw["geocoder"]),
        )

        result = engine.plan_dispatch(
            build_orders(raw["orders"]),
            build_drivers(raw["drivers"]),
            build_vehicles(raw["vehicles"]),
        )

        self.assertEqual(20, len(raw["orders"]))
        self.assertGreaterEqual(len(result.plans), 1)
        self.assertEqual("1HF8JY", raw["vehicles"][0]["metadata"]["rego"])

    def test_legacy_service_minutes_input_is_ignored(self) -> None:
        raw_orders = [
            {
                "order_id": 9,
                "dispatch_date": DISPATCH_DATE.isoformat(),
                "delivery_address": "Alpha",
                "lat": -37.80,
                "lng": 144.95,
                "zone_code": "LOCAL",
                "urgency": "NORMAL",
                "window_start": "08:00",
                "window_end": "11:00",
                "load_type": "MIXED",
                "kg_count": 0,
                "pallet_count": 1,
                "bag_count": 0,
                "service_minutes": 45,
                "postcode": "3000",
            },
            {
                "order_id": 10,
                "dispatch_date": DISPATCH_DATE.isoformat(),
                "delivery_address": "Bravo",
                "lat": -37.81,
                "lng": 144.96,
                "zone_code": "LOCAL",
                "urgency": "NORMAL",
                "window_start": "08:00",
                "window_end": "12:00",
                "load_type": "MIXED",
                "kg_count": 0,
                "pallet_count": 1,
                "bag_count": 0,
                "service_minutes": -3,
                "postcode": "3000",
            },
        ]
        orders = build_orders(raw_orders)
        drivers = [self._driver(1)]
        vehicles = [self._vehicle(500, pallet_capacity=4, tub_capacity=8)]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)

        self.assertEqual(1, len(result.plans))
        self.assertEqual({9, 10}, set(result.plans[0].order_ids))
        self.assertEqual(2, result.plans[0].total_orders)
        self.assertEqual((), result.plans[0].stop_sequence)
        self.assertEqual({}, result.plans[0].etas)

    def test_legacy_zone_ids_can_convert_with_legacy_map(self) -> None:
        raw = json.loads(Path("examples/sample-dispatch-input-legacy-zone-id.json").read_text(encoding="utf-8"))
        drivers = build_drivers(raw["drivers"])
        self.assertEqual((), drivers[0].preferred_zone_codes)

        mapped_drivers = build_drivers_with_legacy(raw["drivers"], legacy_zone_code_by_id=raw["legacy_zone_code_by_id"])
        self.assertEqual(("LOCAL",), mapped_drivers[0].preferred_zone_codes)

    def test_order_assignments_match_dispatch_plan(self) -> None:
        orders = [
            self._order(11, "Alpha", "08:00", "12:00", pallet_count=1),
            self._order(12, "Bravo", "08:00", "12:00", pallet_count=1),
        ]
        drivers = [self._driver(1)]
        vehicles = [self._vehicle(600, pallet_capacity=4, tub_capacity=8)]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)

        self.assertEqual(1, len(result.plans))
        self.assertEqual(2, len(result.order_assignments))
        assignment_by_order = {item.order_id: item for item in result.order_assignments}
        for order_id in result.plans[0].order_ids:
            assignment = assignment_by_order[order_id]
            self.assertEqual(result.plans[0].plan_id, assignment.plan_id)
            self.assertEqual(result.plans[0].driver_id, assignment.driver_id)
            self.assertEqual(result.plans[0].vehicle_id, assignment.vehicle_id)
            self.assertIsNone(assignment.stop_sequence)
            self.assertIsNone(assignment.eta)
            self.assertIsNone(assignment.departure)

    def test_cli_serialization_contains_order_assignments(self) -> None:
        orders = [self._order(13, "Alpha", "08:00", "12:00", pallet_count=1)]
        drivers = [self._driver(1)]
        vehicles = [self._vehicle(700, pallet_capacity=3, tub_capacity=4)]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)
        payload = serialize_result(result)

        self.assertIn("order_assignments", payload)
        self.assertEqual(1, len(payload["order_assignments"]))
        self.assertEqual(13, payload["order_assignments"][0]["order_id"])
        self.assertEqual("3000", payload["order_assignments"][0]["postcode"])
        self.assertEqual("LOCAL", payload["order_assignments"][0]["zone_code"])
        self.assertIsNone(payload["order_assignments"][0]["eta"])
        self.assertIsNone(payload["order_assignments"][0]["departure"])
        self.assertIn("plan_id", payload["order_assignments"][0])
        self.assertNotIn("run_id", payload["order_assignments"][0])
        self.assertIsNone(payload["plans"][0]["planned_start"])
        self.assertEqual([], payload["plans"][0]["stop_sequence"])
        self.assertEqual({}, payload["plans"][0]["etas"])
        self.assertIn("plan_id", payload["plans"][0])
        self.assertNotIn("run_id", payload["plans"][0])
        self.assertIn("order_ids", payload["plans"][0])
        self.assertIn("total_orders", payload["plans"][0])
        self.assertIn("time_window_start", payload["plans"][0])
        self.assertIn("time_window_end", payload["plans"][0])
        self.assertIn("urgent_order_count", payload["plans"][0])

    def test_output_contract_keys_plan_links_and_unique_assigned_orders(self) -> None:
        orders = [
            self._order(1301, "Alpha", "08:00", "12:00", pallet_count=1),
            self._order(1302, "Bravo", "08:00", "12:00", pallet_count=1),
        ]
        drivers = [self._driver(1)]
        vehicles = [self._vehicle(1700, pallet_capacity=6, tub_capacity=8)]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)
        payload = serialize_result(result)

        self.assertEqual({"plans", "order_assignments", "exceptions"}, set(payload.keys()))
        self.assertTrue(all("plan_id" in item for item in payload["plans"]))
        self.assertTrue(all("run_id" not in item for item in payload["plans"]))
        self.assertTrue(all("plan_id" in item for item in payload["order_assignments"]))
        self.assertTrue(all("run_id" not in item for item in payload["order_assignments"]))

        plan_ids = {item["plan_id"] for item in payload["plans"]}
        self.assertTrue(all(item["plan_id"] in plan_ids for item in payload["order_assignments"]))

        assigned_order_ids = [item["order_id"] for item in payload["order_assignments"]]
        self.assertEqual(len(assigned_order_ids), len(set(assigned_order_ids)))

    def test_plans_are_aggregated_by_dispatch_date_driver_vehicle(self) -> None:
        plan_a = DispatchPlan(
            plan_id="PLAN-A",
            dispatch_date=DISPATCH_DATE,
            driver_id=1,
            vehicle_id=500,
            order_ids=(4101,),
            total_orders=1,
            load_summary={"kg": 0.0, "pallets": 1, "tubs": 0, "loose_units": 0, "trolleys": 0, "stillages": 0},
            zone_code="LOCAL",
            time_window_start=self._to_minutes("08:00"),
            time_window_end=self._to_minutes("09:00"),
            urgent_order_count=0,
            objective_score=100,
            explanation=("first",),
            stop_sequence=(),
            etas={},
            planned_start=None,
            planned_finish=None,
        )
        plan_b = DispatchPlan(
            plan_id="PLAN-B",
            dispatch_date=DISPATCH_DATE,
            driver_id=1,
            vehicle_id=500,
            order_ids=(4102,),
            total_orders=1,
            load_summary={"kg": 0.0, "pallets": 2, "tubs": 0, "loose_units": 0, "trolleys": 0, "stillages": 0},
            zone_code="WEST",
            time_window_start=self._to_minutes("10:00"),
            time_window_end=self._to_minutes("11:00"),
            urgent_order_count=1,
            objective_score=200,
            explanation=("second",),
            stop_sequence=(),
            etas={},
            planned_start=None,
            planned_finish=None,
        )
        assignment_a = DispatchOrderAssignment(
            order_id=4101,
            plan_id="PLAN-A",
            dispatch_date=DISPATCH_DATE,
            driver_id=1,
            vehicle_id=500,
            objective_score=100,
            postcode="3000",
            zone_code="LOCAL",
            status="ASSIGNED",
            explanation=("first",),
            stop_sequence=None,
            eta=None,
            departure=None,
            planned_start=None,
            planned_finish=None,
        )
        assignment_b = DispatchOrderAssignment(
            order_id=4102,
            plan_id="PLAN-B",
            dispatch_date=DISPATCH_DATE,
            driver_id=1,
            vehicle_id=500,
            objective_score=200,
            postcode="3030",
            zone_code="WEST",
            status="ASSIGNED",
            explanation=("second",),
            stop_sequence=None,
            eta=None,
            departure=None,
            planned_start=None,
            planned_finish=None,
        )

        aggregated_plans, remapped_assignments = DispatchEngine._aggregate_plans_and_assignments(
            [plan_a, plan_b],
            [assignment_a, assignment_b],
        )

        self.assertEqual(1, len(aggregated_plans))
        aggregate = aggregated_plans[0]
        self.assertEqual(DISPATCH_DATE, aggregate.dispatch_date)
        self.assertEqual(1, aggregate.driver_id)
        self.assertEqual(500, aggregate.vehicle_id)
        self.assertEqual((4101, 4102), aggregate.order_ids)
        self.assertEqual(2, aggregate.total_orders)
        self.assertEqual("MULTI_ZONE", aggregate.zone_code)
        self.assertEqual(300, aggregate.objective_score)
        self.assertTrue(all(item.plan_id == aggregate.plan_id for item in remapped_assignments))

    def test_unknown_postcode_returns_postcode_not_mapped_exception(self) -> None:
        orders = [self._order(14, "Alpha", "08:00", "10:00", postcode="9999", zone_code=None)]
        drivers = [self._driver(1)]
        vehicles = [self._vehicle(800, pallet_capacity=3, tub_capacity=4)]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)

        self.assertEqual(0, len(result.plans))
        self.assertTrue(any(exc.reason_code == "POSTCODE_NOT_MAPPED" for exc in result.exceptions))

    def test_driver_utilization_prefers_using_multiple_drivers_when_feasible(self) -> None:
        orders = [
            self._order(141, "Alpha", "08:00", "11:00", postcode=None, zone_code="LOCAL"),
            self._order(142, "Bravo", "08:00", "11:00", postcode=None, zone_code="WEST"),
        ]
        drivers = [self._driver(1), self._driver(2)]
        vehicles = [
            self._vehicle(801, pallet_capacity=3, tub_capacity=4),
            self._vehicle(802, pallet_capacity=3, tub_capacity=4),
        ]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)

        self.assertEqual(2, len(result.plans))
        self.assertEqual(2, len({plan.driver_id for plan in result.plans}))
        self.assertFalse(any(exc.reason_code.startswith("DRIVER_UNUSED") for exc in result.exceptions))

    def test_unused_driver_outscored_reason_is_reported(self) -> None:
        orders = [self._order(143, "Alpha", "08:00", "11:00", postcode=None, zone_code="LOCAL")]
        drivers = [self._driver(1), self._driver(2)]
        vehicles = [self._vehicle(803, pallet_capacity=4, tub_capacity=8)]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)

        self.assertEqual(1, len(result.plans))
        self.assertTrue(any(exc.reason_code == "DRIVER_UNUSED_OUTSCORED" for exc in result.exceptions))

    def test_unused_driver_no_remaining_run_reason_is_reported(self) -> None:
        orders = [self._order(144, "Alpha", "08:00", "11:00", designated_driver_id=1, postcode=None, zone_code="LOCAL")]
        drivers = [self._driver(1), self._driver(2)]
        vehicles = [self._vehicle(804, pallet_capacity=4, tub_capacity=8)]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)

        self.assertEqual(1, len(result.plans))
        self.assertTrue(any(exc.reason_code == "DRIVER_UNUSED_NO_REMAINING_RUN" for exc in result.exceptions))

    def test_utilization_split_can_expand_runs_when_driver_gap_exists(self) -> None:
        order_a = self._order(145, "Alpha", "08:00", "11:00", pallet_count=1, postcode=None, zone_code="LOCAL")
        order_b = self._order(146, "Bravo", "08:00", "11:00", pallet_count=1, postcode=None, zone_code="LOCAL")
        run = self._make_run("RUN-UTIL-1", [order_a, order_b])
        drivers = [self._driver(1), self._driver(2)]
        vehicles = [
            self._vehicle(805, pallet_capacity=4, tub_capacity=8),
            self._vehicle(806, pallet_capacity=4, tub_capacity=8),
        ]

        updated_runs, generated_runs = self.engine._maybe_split_for_driver_utilization([run], drivers, vehicles)

        self.assertGreaterEqual(len(updated_runs), 2)
        self.assertGreaterEqual(len(generated_runs), 2)
        self.assertTrue(any("-R" in split_run.run_id for split_run in generated_runs))

    def test_urgent_run_priority_when_resources_conflict(self) -> None:
        orders = [
            self._order(15, "Alpha", "08:00", "08:25", urgency=Urgency.URGENT, postcode=None, zone_code="LOCAL"),
            self._order(16, "Bravo", "08:00", "08:25", urgency=Urgency.NORMAL, postcode=None, zone_code="WEST"),
        ]
        drivers = [self._driver(1)]
        vehicles = [self._vehicle(900, pallet_capacity=4, tub_capacity=8)]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)

        self.assertEqual(1, len(result.plans))
        self.assertEqual({15}, {item.order_id for item in result.order_assignments})

    def test_designated_run_priority_under_conflict(self) -> None:
        orders = [
            self._order(17, "Far", "08:00", "09:45", urgency=Urgency.NORMAL, designated_driver_id=1, postcode=None, zone_code="LOCAL"),
            self._order(18, "Alpha", "08:00", "09:45", urgency=Urgency.NORMAL, postcode=None, zone_code="WEST"),
        ]
        drivers = [self._driver(1)]
        vehicles = [self._vehicle(901, pallet_capacity=4, tub_capacity=8)]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)

        self.assertEqual(1, len(result.plans))
        self.assertEqual({17}, {item.order_id for item in result.order_assignments})

    def test_run_generation_splits_spatially_dispersed_orders(self) -> None:
        orders = [
            self._order(19, "Alpha", "09:00", "11:00", pallet_count=1, postcode=None, zone_code="LOCAL"),
            self._order(20, "Remote", "09:00", "11:00", pallet_count=1, postcode=None, zone_code="LOCAL"),
        ]
        drivers = [self._driver(1), self._driver(2)]
        vehicles = [self._vehicle(902, pallet_capacity=4, tub_capacity=8)]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)

        self.assertGreaterEqual(len(result.runs), 2)

    def test_run_generation_uses_real_vehicle_feasibility_not_fleet_envelope_only(self) -> None:
        orders = [
            self._order(21, "Alpha", "09:00", "11:00", pallet_count=8, postcode=None, zone_code="LOCAL"),
            self._order(22, "Bravo", "09:00", "11:00", load_type=LoadType.MIXED, bag_count=48, postcode=None, zone_code="LOCAL"),
        ]
        drivers = [self._driver(1), self._driver(2)]
        vehicles = [
            self._vehicle(903, pallet_capacity=8, tub_capacity=0),
            self._vehicle(904, pallet_capacity=0, tub_capacity=24),
        ]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)

        self.assertGreaterEqual(len(result.runs), 2)
        self.assertFalse(any(exc.reason_code == "NO_FEASIBLE_VEHICLE" for exc in result.exceptions))

    def test_repair_prefers_removing_non_urgent_non_designated_order(self) -> None:
        protected = self._order(
            23,
            "Alpha",
            "08:00",
            "10:00",
            urgency=Urgency.URGENT,
            designated_driver_id=1,
            pallet_count=1,
            postcode=None,
            zone_code="LOCAL",
        )
        removable = self._order(
            24,
            "Far",
            "08:00",
            "10:00",
            urgency=Urgency.NORMAL,
            designated_driver_id=None,
            pallet_count=1,
            postcode=None,
            zone_code="LOCAL",
        )
        run = self._make_run("RUN-REPAIR-1", [protected, removable], designated_driver_id=1)

        repaired = self.engine._repair_run(run)

        self.assertEqual(2, len(repaired))
        isolated_order_ids = [order.order_id for order in repaired[1].orders]
        self.assertEqual([24], isolated_order_ids)

    def test_repair_has_fallback_when_only_protected_orders(self) -> None:
        protected_a = self._order(25, "Alpha", "08:00", "10:00", urgency=Urgency.URGENT, designated_driver_id=1, postcode=None, zone_code="LOCAL")
        protected_b = self._order(26, "Bravo", "08:00", "10:00", urgency=Urgency.URGENT, designated_driver_id=1, postcode=None, zone_code="LOCAL")
        run = self._make_run("RUN-REPAIR-2", [protected_a, protected_b], designated_driver_id=1)

        repaired = self.engine._repair_run(run)

        self.assertEqual(2, len(repaired))
        self.assertEqual(2, sum(len(item.orders) for item in repaired))

    def test_trip_summary_output_no_longer_requires_route_cache(self) -> None:
        orders = [self._order(27, "Alpha", "08:00", "11:00", pallet_count=1)]
        drivers = [self._driver(1)]
        vehicles = [self._vehicle(905, pallet_capacity=3, tub_capacity=4)]

        result = self.engine.plan_dispatch(orders, drivers, vehicles)

        self.assertEqual(1, len(result.plans))
        self.assertEqual((27,), result.plans[0].order_ids)
        self.assertEqual((), result.plans[0].stop_sequence)

    def _order(
        self,
        order_id: int,
        address: str,
        window_start: str,
        window_end: str,
        pallet_count: int = 0,
        bag_count: int = 0,
        kg_count: int = 0,
        designated_driver_id: int | None = None,
        load_type: LoadType = LoadType.MIXED,
        urgency: Urgency = Urgency.NORMAL,
        postcode: str | None = "3000",
        zone_code: str | None = "LOCAL",
    ) -> DispatchOrder:
        coordinates = {
            "Alpha": (-37.80, 144.95),
            "Bravo": (-37.81, 144.96),
            "Heavy": (-37.82, 144.97),
            "Near": (-37.83, 144.98),
            "Far": (-37.90, 145.10),
            "Remote": (-38.60, 146.30),
            "Loose": (-37.79, 144.94),
        }
        lat, lng = coordinates[address]
        return DispatchOrder(
            order_id=order_id,
            dispatch_date=DISPATCH_DATE,
            delivery_address=address,
            lat=lat,
            lng=lng,
            zone_code=zone_code,
            urgency=urgency,
            window_start=self._to_minutes(window_start),
            window_end=self._to_minutes(window_end),
            designated_driver_id=designated_driver_id,
            load_type=load_type,
            pallet_count=pallet_count,
            bag_count=bag_count,
            kg_count=kg_count,
            postcode=postcode,
        )

    def _make_run(
        self,
        run_id: str,
        orders: list[DispatchOrder],
        designated_driver_id: int | None = None,
    ) -> DispatchRun:
        load = self.engine.snapshot_builder.compute_load(orders[0])
        for order in orders[1:]:
            load = load + self.engine.snapshot_builder.compute_load(order)
        return DispatchRun(
            run_id=run_id,
            dispatch_date=orders[0].dispatch_date,
            zone_code=str(orders[0].zone_code),
            bucket_start=orders[0].window_start,
            bucket_end=orders[0].window_end,
            orders=list(orders),
            load=load,
            estimated_service_minutes=len(orders) * FIXED_STOP_MINUTES,
            designated_driver_id=designated_driver_id,
        )

    def _driver(
        self,
        driver_id: int,
        preferred_zone_codes: tuple[str, ...] = (),
        historical_vehicle_ids: tuple[int, ...] = (),
        is_available: bool = True,
    ) -> DispatchDriver:
        return DispatchDriver(
            driver_id=driver_id,
            shift_start=self._to_minutes("07:30"),
            shift_end=self._to_minutes("17:00"),
            is_available=is_available,
            start_location="Depot",
            end_location="Depot",
            preferred_zone_codes=preferred_zone_codes,
            historical_vehicle_ids=historical_vehicle_ids,
            start_lat=-37.78,
            start_lng=144.93,
            end_lat=-37.78,
            end_lng=144.93,
        )

    def _vehicle(
        self,
        vehicle_id: int,
        pallet_capacity: int,
        tub_capacity: int = 0,
        kg_capacity: int = 1000,
    ) -> DispatchVehicle:
        return DispatchVehicle(
            vehicle_id=vehicle_id,
            vehicle_type="van",
            is_available=True,
            kg_capacity=kg_capacity,
            pallet_capacity=pallet_capacity,
            tub_capacity=tub_capacity,
        )

    @staticmethod
    def _to_minutes(value: str) -> int:
        hours, minutes = value.split(":")
        return int(hours) * 60 + int(minutes)


class AssignmentSolverVehicleSwitchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.solver = AssignmentSolver(ScoringPolicy(vehicle_switch_penalty=2000, vehicle_switch_proxy_penalty=2000))
        self.driver_1 = DispatchDriver(
            driver_id=1,
            shift_start=0,
            shift_end=24 * 60,
            is_available=True,
            start_location="Depot",
            end_location="Depot",
            start_lat=-37.78,
            start_lng=144.93,
            end_lat=-37.78,
            end_lng=144.93,
        )
        self.driver_2 = DispatchDriver(
            driver_id=2,
            shift_start=0,
            shift_end=24 * 60,
            is_available=True,
            start_location="Depot",
            end_location="Depot",
            start_lat=-37.78,
            start_lng=144.93,
            end_lat=-37.78,
            end_lng=144.93,
        )
        self.vehicles = {
            1: DispatchVehicle(vehicle_id=1, vehicle_type="van", is_available=True, pallet_capacity=5, tub_capacity=5),
            2: DispatchVehicle(vehicle_id=2, vehicle_type="van", is_available=True, pallet_capacity=5, tub_capacity=5),
            3: DispatchVehicle(vehicle_id=3, vehicle_type="van", is_available=True, pallet_capacity=5, tub_capacity=5),
        }

    def test_same_day_prefers_same_vehicle_for_consecutive_runs(self) -> None:
        run_a = self._run("RUN-A", date(2026, 4, 22), "08:00", "09:00")
        run_b = self._run("RUN-B", date(2026, 4, 22), "09:10", "10:10")
        context = self._context([run_a, run_b])
        candidates = [
            self._candidate("RUN-A", driver_id=1, vehicle_id=1, start="08:00", finish="09:00", objective=10000),
            self._candidate("RUN-B", driver_id=1, vehicle_id=1, start="09:10", finish="10:10", objective=9000),
            self._candidate("RUN-B", driver_id=1, vehicle_id=2, start="09:10", finish="10:10", objective=10500),
        ]

        selected = self.solver._solve_greedily(candidates, context)
        by_run = {candidate.run_id: candidate for candidate in selected}

        self.assertEqual(2, len(selected))
        self.assertEqual(1, by_run["RUN-B"].vehicle_id)

    def test_switch_penalty_does_not_accumulate_across_days(self) -> None:
        run_day_1 = self._run("RUN-D1", date(2026, 4, 22), "08:00", "09:00")
        run_day_2 = self._run("RUN-D2", date(2026, 4, 23), "08:00", "09:00")
        context = self._context([run_day_1, run_day_2])
        candidates = [
            self._candidate("RUN-D1", driver_id=1, vehicle_id=1, start="08:00", finish="09:00", objective=9000),
            self._candidate("RUN-D2", driver_id=1, vehicle_id=1, start="08:00", finish="09:00", objective=9000),
            self._candidate("RUN-D2", driver_id=1, vehicle_id=2, start="08:00", finish="09:00", objective=10500),
        ]

        selected = self.solver._solve_greedily(candidates, context)
        by_run = {candidate.run_id: candidate for candidate in selected}

        self.assertEqual(2, len(selected))
        self.assertEqual(2, by_run["RUN-D2"].vehicle_id)

    def test_adjacent_switch_order_uses_start_finish_run_id_stable_sort(self) -> None:
        existing = [
            self._candidate("RUN-B", driver_id=1, vehicle_id=1, start="08:00", finish="09:00", objective=1000),
        ]
        candidate_a = self._candidate("RUN-A", driver_id=1, vehicle_id=2, start="08:00", finish="09:00", objective=1000)
        candidate_c = self._candidate("RUN-C", driver_id=1, vehicle_id=1, start="08:00", finish="09:00", objective=1000)

        delta_a = self.solver._delta_switches_after_insertion(existing, candidate_a)
        delta_c = self.solver._delta_switches_after_insertion(existing, candidate_c)

        self.assertEqual(1, delta_a)
        self.assertEqual(0, delta_c)

    def test_greedy_allows_business_priority_after_zone_keys(self) -> None:
        solver = AssignmentSolver(
            ScoringPolicy(
                vehicle_switch_penalty=0,
                vehicle_switch_proxy_penalty=0,
                driver_balance_penalty_per_min=0,
            )
        )
        run_a = self._run("RUN-A", date(2026, 4, 22), "08:00", "09:00")
        run_b = self._run("RUN-B", date(2026, 4, 22), "09:10", "10:10")
        context = self._context([run_a, run_b])
        candidates = [
            self._candidate("RUN-A", driver_id=1, vehicle_id=1, start="08:00", finish="09:00", objective=1000),
            self._candidate("RUN-B", driver_id=1, vehicle_id=1, start="09:10", finish="10:10", objective=1000),
            self._candidate("RUN-B", driver_id=1, vehicle_id=2, start="09:10", finish="10:10", objective=5000),
        ]

        selected = solver._solve_greedily(candidates, context)
        by_run = {candidate.run_id: candidate for candidate in selected}

        self.assertEqual(2, len(selected))
        self.assertEqual(2, by_run["RUN-B"].vehicle_id)

    def test_greedy_tie_on_switch_delta_uses_business_then_finish(self) -> None:
        run_a = self._run("RUN-T1", date(2026, 4, 22), "08:00", "09:00")
        run_b = self._run("RUN-T2", date(2026, 4, 22), "09:10", "11:00")
        context = self._context([run_a, run_b])
        candidates = [
            self._candidate("RUN-T1", driver_id=1, vehicle_id=1, start="08:00", finish="09:00", objective=1000),
            self._candidate("RUN-T2", driver_id=1, vehicle_id=1, start="09:10", finish="10:40", objective=1200),
            self._candidate("RUN-T2", driver_id=1, vehicle_id=1, start="09:10", finish="10:20", objective=1200),
            self._candidate("RUN-T2", driver_id=1, vehicle_id=1, start="09:10", finish="10:10", objective=1000),
        ]

        selected = self.solver._solve_greedily(candidates, context)
        run_t2 = next(candidate for candidate in selected if candidate.run_id == "RUN-T2")
        self.assertEqual(self._to_minutes("10:20"), run_t2.estimated_finish)

    def test_greedy_prefers_same_zone_continuity_before_unused_driver_when_zone_tied(self) -> None:
        run_a = self._run("RUN-GA", date(2026, 4, 22), "08:00", "09:00")
        run_b = self._run("RUN-GB", date(2026, 4, 22), "09:10", "10:10")
        context = self._context([run_a, run_b])
        candidates = [
            self._candidate("RUN-GA", driver_id=1, vehicle_id=1, start="08:00", finish="09:00", objective=1200),
            self._candidate("RUN-GB", driver_id=1, vehicle_id=1, start="09:10", finish="10:10", objective=5000),
            self._candidate("RUN-GB", driver_id=2, vehicle_id=2, start="09:10", finish="10:10", objective=1500),
        ]

        selected = self.solver._solve_greedily(candidates, context)
        by_run = {candidate.run_id: candidate for candidate in selected}

        self.assertEqual(2, len(selected))
        self.assertEqual(1, by_run["RUN-GB"].driver_id)

    def test_greedy_prefers_same_zone_continuity_before_unused_driver_bonus(self) -> None:
        solver = AssignmentSolver(ScoringPolicy())
        run_a = self._run("RUN-ZA", date(2026, 4, 22), "08:00", "09:00", zone_code="LOCAL")
        run_b = self._run("RUN-ZB", date(2026, 4, 22), "09:10", "10:10", zone_code="LOCAL")
        custom_driver_1 = replace(self.driver_1, preferred_zone_codes=("LOCAL",))
        custom_driver_2 = replace(self.driver_2, preferred_zone_codes=("LOCAL",))
        context = self._context([run_a, run_b], drivers_by_id={1: custom_driver_1, 2: custom_driver_2})
        candidates = [
            self._candidate("RUN-ZA", driver_id=1, vehicle_id=1, start="08:00", finish="09:00", objective=2000, preferred_zone_match=1),
            self._candidate("RUN-ZA", driver_id=2, vehicle_id=2, start="08:00", finish="09:00", objective=1900, preferred_zone_match=1),
            self._candidate("RUN-ZB", driver_id=1, vehicle_id=1, start="09:10", finish="10:10", objective=1000, preferred_zone_match=1),
            self._candidate("RUN-ZB", driver_id=2, vehicle_id=2, start="09:10", finish="10:10", objective=5000, preferred_zone_match=1),
        ]

        selected = solver._solve_greedily(candidates, context)
        by_run = {candidate.run_id: candidate for candidate in selected}

        self.assertEqual(2, len(selected))
        self.assertEqual(1, by_run["RUN-ZA"].driver_id)
        self.assertEqual(1, by_run["RUN-ZB"].driver_id)

    @unittest.skipUnless(ORTOOLS_CP_SAT_AVAILABLE, "OR-Tools CP-SAT is not available")
    def test_cp_sat_lexicographic_minimizes_driver_day_vehicle_count_before_objective(self) -> None:
        run_a = self._run("RUN-CP-A", date(2026, 4, 22), "08:00", "09:00")
        run_b = self._run("RUN-CP-B", date(2026, 4, 22), "09:10", "10:10")
        run_a.designated_driver_id = 1
        run_b.designated_driver_id = 1
        context = self._context([run_a, run_b])
        candidates = [
            self._candidate("RUN-CP-A", driver_id=1, vehicle_id=1, start="08:00", finish="09:00", objective=1000),
            self._candidate("RUN-CP-B", driver_id=1, vehicle_id=1, start="09:10", finish="10:10", objective=1000),
            self._candidate("RUN-CP-B", driver_id=1, vehicle_id=2, start="09:10", finish="10:10", objective=5000),
        ]

        selected = self.solver._solve_with_cp_sat(candidates, context)
        by_run = {candidate.run_id: candidate for candidate in selected}
        self.assertEqual(2, len(selected))
        self.assertEqual(1, by_run["RUN-CP-B"].vehicle_id)

    @unittest.skipUnless(ORTOOLS_CP_SAT_AVAILABLE, "OR-Tools CP-SAT is not available")
    def test_cp_sat_lexicographic_uses_objective_when_switch_proxy_ties(self) -> None:
        run_a = self._run("RUN-CP-C", date(2026, 4, 22), "08:00", "09:00")
        run_b = self._run("RUN-CP-D", date(2026, 4, 22), "09:10", "10:10")
        run_a.designated_driver_id = 1
        run_b.designated_driver_id = 1
        context = self._context([run_a, run_b])
        candidates = [
            self._candidate("RUN-CP-C", driver_id=1, vehicle_id=1, start="08:00", finish="09:00", objective=1000),
            self._candidate("RUN-CP-D", driver_id=1, vehicle_id=1, start="09:10", finish="10:10", objective=1000),
            self._candidate("RUN-CP-D", driver_id=1, vehicle_id=1, start="09:10", finish="10:10", objective=2200),
        ]

        selected = self.solver._solve_with_cp_sat(candidates, context)
        run_cp_d = next(candidate for candidate in selected if candidate.run_id == "RUN-CP-D")
        self.assertEqual(2200, run_cp_d.objective_score)

    @unittest.skipUnless(ORTOOLS_CP_SAT_AVAILABLE, "OR-Tools CP-SAT is not available")
    def test_cp_sat_prioritizes_used_driver_count_before_ordinary_objective(self) -> None:
        run_a = self._run("RUN-CP-U1", date(2026, 4, 22), "08:00", "09:00")
        run_b = self._run("RUN-CP-U2", date(2026, 4, 22), "09:20", "10:20")
        context = self._context([run_a, run_b])
        candidates = [
            self._candidate("RUN-CP-U1", driver_id=1, vehicle_id=1, start="08:00", finish="09:00", objective=3000),
            self._candidate("RUN-CP-U1", driver_id=2, vehicle_id=1, start="08:00", finish="09:00", objective=500),
            self._candidate("RUN-CP-U2", driver_id=1, vehicle_id=1, start="09:20", finish="10:20", objective=3000),
            self._candidate("RUN-CP-U2", driver_id=2, vehicle_id=1, start="09:20", finish="10:20", objective=500),
        ]

        selected = self.solver._solve_with_cp_sat(candidates, context)

        self.assertEqual(2, len(selected))
        self.assertEqual(2, len({candidate.driver_id for candidate in selected}))

    def test_switch_explanation_marks_forced_when_resource_conflict_blocks_same_vehicle(self) -> None:
        run_a = self._run("RUN-A", date(2026, 4, 22), "08:00", "09:00")
        run_b = self._run("RUN-B", date(2026, 4, 22), "09:10", "10:10")
        run_block = self._run("RUN-BLOCK", date(2026, 4, 22), "09:05", "11:40")
        context = self._context([run_a, run_b, run_block])

        selected = [
            self._candidate("RUN-A", driver_id=1, vehicle_id=1, start="08:00", finish="09:00", objective=1000),
            self._candidate("RUN-B", driver_id=1, vehicle_id=2, start="09:10", finish="10:10", objective=1000),
            self._candidate("RUN-BLOCK", driver_id=2, vehicle_id=1, start="09:05", finish="11:40", objective=1000),
        ]
        all_candidates = [
            *selected,
            self._candidate("RUN-B", driver_id=1, vehicle_id=1, start="09:10", finish="10:10", objective=1000),
        ]

        annotated = self.solver._annotate_vehicle_switch_explanations(selected, all_candidates, context)
        run_b_candidate = next(item for item in annotated if item.run_id == "RUN-B")
        explanation = " ".join(run_b_candidate.explanation)

        self.assertIn("Vehicle switch applied between consecutive runs for this driver.", explanation)
        self.assertIn("Switched vehicle due to feasibility/resource constraints.", explanation)

    def test_switch_explanation_marks_same_vehicle_continuity(self) -> None:
        run_a = self._run("RUN-X", date(2026, 4, 22), "08:00", "09:00")
        run_b = self._run("RUN-Y", date(2026, 4, 22), "09:10", "10:10")
        context = self._context([run_a, run_b])
        selected = [
            self._candidate("RUN-X", driver_id=1, vehicle_id=1, start="08:00", finish="09:00", objective=1000),
            self._candidate("RUN-Y", driver_id=1, vehicle_id=1, start="09:10", finish="10:10", objective=1000),
        ]

        annotated = self.solver._annotate_vehicle_switch_explanations(selected, selected, context)
        run_b_candidate = next(item for item in annotated if item.run_id == "RUN-Y")
        explanation = " ".join(run_b_candidate.explanation)
        self.assertIn("Kept same vehicle across consecutive runs for this driver.", explanation)

    def _context(
        self,
        runs: list[DispatchRun],
        drivers_by_id: dict[int, DispatchDriver] | None = None,
    ) -> AssignmentContext:
        return AssignmentContext(
            drivers_by_id=drivers_by_id or {1: self.driver_1, 2: self.driver_2},
            vehicles_by_id=self.vehicles,
            runs_by_id={run.run_id: run for run in runs},
        )

    def _run(
        self,
        run_id: str,
        dispatch_day: date,
        window_start: str,
        window_end: str,
        zone_code: str = "LOCAL",
    ) -> DispatchRun:
        order = DispatchOrder(
            order_id=abs(hash((run_id, "order"))) % 1_000_000,
            dispatch_date=dispatch_day,
            delivery_address=f"{run_id}-address",
            lat=-37.80,
            lng=144.95,
            zone_code=zone_code,
            urgency=Urgency.NORMAL,
            window_start=self._to_minutes(window_start),
            window_end=self._to_minutes(window_end),
            load_type=LoadType.MIXED,
            pallet_count=1,
            bag_count=1,
            postcode="3000",
        )
        return DispatchRun(
            run_id=run_id,
            dispatch_date=dispatch_day,
            zone_code=zone_code,
            bucket_start=order.window_start,
            bucket_end=order.window_end,
            orders=[order],
            load=LoadVector(pallets=1),
            estimated_service_minutes=FIXED_STOP_MINUTES,
            designated_driver_id=None,
        )

    @staticmethod
    def _candidate(
        run_id: str,
        driver_id: int,
        vehicle_id: int,
        start: str,
        finish: str,
        objective: int,
        preferred_zone_match: int = 0,
    ) -> CandidateAssignment:
        def to_minutes(value: str) -> int:
            hours, minutes = value.split(":")
            return int(hours) * 60 + int(minutes)

        return CandidateAssignment(
            run_id=run_id,
            driver_id=driver_id,
            vehicle_id=vehicle_id,
            estimated_start=to_minutes(start),
            estimated_finish=to_minutes(finish),
            travel_minutes=0,
            deadhead_minutes=0,
            work_minutes=to_minutes(finish) - to_minutes(start),
            capacity_waste=0,
            preferred_zone_match=preferred_zone_match,
            continuity_match=0,
            objective_score=objective,
            run_priority_score=0,
            efficiency_score=0,
            explanation=("Base explanation.",),
        )

    @staticmethod
    def _to_minutes(value: str) -> int:
        hours, minutes = value.split(":")
        return int(hours) * 60 + int(minutes)


if __name__ == "__main__":
    unittest.main()
