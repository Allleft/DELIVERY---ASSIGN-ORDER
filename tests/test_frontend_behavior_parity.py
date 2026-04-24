from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


def _run_frontend_probe(
    script_body: str,
    include_overrides: bool = True,
    include_summary_module: bool = True,
    include_zone_module: bool = True,
) -> dict:
    script = f"""
const fs = require('fs');
const vm = require('vm');
const elements = {{}};
function makeElement() {{
  return {{
    addEventListener: () => {{}},
    value: '',
    textContent: '',
    innerHTML: '',
    className: '',
    classList: {{ add: () => {{}}, remove: () => {{}} }},
  }};
}}
const context = {{ console }};
context.document = {{
  addEventListener: () => {{}},
  createElement: () => ({{ click: () => {{}} }}),
  body: {{ appendChild: () => {{}}, removeChild: () => {{}} }},
  getElementById: (id) => {{
    if (!elements[id]) elements[id] = makeElement();
    return elements[id];
  }},
}};
context.URL = {{ createObjectURL: () => '', revokeObjectURL: () => {{}} }};
context.Blob = function Blob() {{}};
context.window = context;
vm.createContext(context);
if ({str(include_zone_module).lower()}) {{
  vm.runInContext(
    fs.readFileSync('frontend/modules/zone-utils.js', 'utf8'),
    context,
    {{ filename: 'frontend/modules/zone-utils.js' }}
  );
}}
if ({str(include_summary_module).lower()}) {{
  vm.runInContext(
    fs.readFileSync('frontend/modules/driver-assignment-summary.js', 'utf8'),
    context,
    {{ filename: 'frontend/modules/driver-assignment-summary.js' }}
  );
}}
vm.runInContext(fs.readFileSync('frontend/app.js', 'utf8'), context, {{ filename: 'frontend/app.js' }});
if ({str(include_overrides).lower()}) {{
  vm.runInContext(fs.readFileSync('frontend/overrides.js', 'utf8'), context, {{ filename: 'frontend/overrides.js' }});
}}
{script_body}
"""
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return json.loads(completed.stdout or "{}")


class FrontendBehaviorParityTest(unittest.TestCase):
    def test_initial_snapshot_orders_empty_and_master_data_visible(self) -> None:
        result = _run_frontend_probe(
            """
const initial = context.createInitialSnapshot();
process.stdout.write(JSON.stringify({
  orders: Array.isArray(initial.orders) ? initial.orders.length : -1,
  drivers: Array.isArray(initial.drivers) ? initial.drivers.length : -1,
  vehicles: Array.isArray(initial.vehicles) ? initial.vehicles.length : -1
}));
"""
        )
        self.assertEqual(0, result["orders"])
        self.assertGreater(result["drivers"], 0)
        self.assertGreater(result["vehicles"], 0)

    def test_driver_assignment_summary_is_default_primary_view(self) -> None:
        html = Path("frontend/index.html").read_text(encoding="utf-8")
        summary_index = html.find("Driver Assignment Summary")
        plans_index = html.find("Assignment Groups (Secondary)")
        self.assertGreaterEqual(summary_index, 0)
        self.assertGreaterEqual(plans_index, 0)
        self.assertLess(summary_index, plans_index)

    def test_postcode_zone_link_and_assignment_empty_hint(self) -> None:
        result = _run_frontend_probe(
            """
const snapshot = context.createInitialSnapshot();
context.applySnapshotToState(snapshot);
context.handleAddOrder();

const zoneCell = { title: '', textContent: '' };
const rowElement = {
  dataset: { index: '0' },
  querySelector: () => zoneCell,
};
const target = {
  dataset: { field: 'postcode' },
  type: 'text',
  value: '3000',
  checked: false,
  closest: () => rowElement,
};
context.handleOrderTableInput({ target });

const container = context.document.getElementById('orderAssignmentsContainer');
context.renderAssignments([], [{ plan_id: 'PLAN-0001' }]);
process.stdout.write(JSON.stringify({
  mapped_zone: zoneCell.title,
  has_aggregation_missing_hint:
    container.innerHTML.includes('Exceptions') || container.innerHTML.includes('Result JSON')
}));
"""
        )
        self.assertEqual("LOCAL", result["mapped_zone"])
        self.assertTrue(result["has_aggregation_missing_hint"])

    def test_core_paths_work_without_runtime_overrides(self) -> None:
        result = _run_frontend_probe(
            """
context.applySnapshotToState(context.createInitialSnapshot());
context.handleAddOrder();
const zoneCell = { title: '', textContent: '' };
const rowElement = {
  dataset: { index: '0' },
  querySelector: () => zoneCell,
};
const target = {
  dataset: { field: 'postcode' },
  type: 'text',
  value: '3000',
  checked: false,
  closest: () => rowElement,
};
context.handleOrderTableInput({ target });
const container = context.document.getElementById('orderAssignmentsContainer');
context.renderAssignments([], [{ plan_id: 'PLAN-0001' }]);
process.stdout.write(JSON.stringify({
  mapped_zone: zoneCell.title,
  has_aggregation_missing_hint:
    container.innerHTML.includes('Exceptions') || container.innerHTML.includes('Result JSON')
}));
""",
            include_overrides=False,
            include_summary_module=False,
            include_zone_module=False,
        )
        self.assertEqual("LOCAL", result["mapped_zone"])
        self.assertTrue(result["has_aggregation_missing_hint"])

    def test_rendered_trip_summary_does_not_show_eta_departure_stop(self) -> None:
        result = _run_frontend_probe(
            """
const plans = [{
  plan_id: 'PLAN-0001',
  dispatch_date: '2026-04-22',
  driver_id: 1,
  vehicle_id: 7,
  order_ids: [2001, 2002],
  total_orders: 2,
  zone_code: 'LOCAL',
  time_window_start: '08:00',
  time_window_end: '10:00',
  urgent_order_count: 1,
  load_summary: { pallets: 2, tubs: 4 },
  objective_score: 12345,
  explanation: ['trip summary'],
  stop_sequence: [],
  etas: {},
  planned_start: null,
  planned_finish: null
}];
const assignments = [{
  order_id: 2001,
  plan_id: 'PLAN-0001',
  dispatch_date: '2026-04-22',
  driver_id: 1,
  vehicle_id: 7,
  status: 'ASSIGNED',
  postcode: '3000',
  zone_code: 'LOCAL',
  objective_score: 12345,
  explanation: ['ok'],
  stop_sequence: null,
  eta: null,
  departure: null,
  planned_start: null,
  planned_finish: null
}];
context.renderAssignments(assignments, plans);
const html = context.document.getElementById('orderAssignmentsContainer').innerHTML;
process.stdout.write(JSON.stringify({
  has_eta: html.includes('ETA'),
  has_departure: html.includes('Departure'),
  has_stop: html.includes('Stop'),
  has_run: html.includes('RUN-') || html.includes('Trip ')
}));
"""
        )
        self.assertFalse(result["has_eta"])
        self.assertFalse(result["has_departure"])
        self.assertFalse(result["has_stop"])
        self.assertFalse(result["has_run"])

    def test_local_planner_reports_unused_driver_reasons(self) -> None:
        result = _run_frontend_probe(
            """
const snapshot = context.createInitialSnapshot();
snapshot.orders = [{
  order_id: 9901,
  dispatch_date: '2026-04-22',
  delivery_address: '328 Swanston Street, Melbourne VIC 3000',
  postcode: '3000',
  urgency: 'NORMAL',
  window_start: '08:00',
  window_end: '11:00',
  designated_driver_id: null,
  load_type: 'MIXED',
  pallet_count: 1,
  bag_count: 0,
  kg_count: 0
}];
const result = context.planDispatch(snapshot);
process.stdout.write(JSON.stringify({
  has_unused_driver_reason: Array.isArray(result.exceptions) && result.exceptions.some((item) => String(item.reason_code || '').startsWith('DRIVER_UNUSED_'))
}));
"""
        )
        self.assertTrue(result["has_unused_driver_reason"])

    def test_local_planner_outputs_plan_id_without_run_id(self) -> None:
        result = _run_frontend_probe(
            """
const snapshot = context.createInitialSnapshot();
snapshot.orders = [{
  order_id: 9101,
  dispatch_date: '2026-04-22',
  delivery_address: '328 Swanston Street, Melbourne VIC 3000',
  postcode: '3000',
  urgency: 'NORMAL',
  window_start: '08:00',
  window_end: '10:00',
  designated_driver_id: null,
  load_type: 'MIXED',
  pallet_count: 1,
  bag_count: 0,
  kg_count: 0
}];
const result = context.planDispatch(snapshot);
const plan = Array.isArray(result.plans) && result.plans.length > 0 ? result.plans[0] : {};
const assignment = Array.isArray(result.order_assignments) && result.order_assignments.length > 0 ? result.order_assignments[0] : {};
process.stdout.write(JSON.stringify({
  has_plan_id: Object.prototype.hasOwnProperty.call(plan, 'plan_id'),
  has_plan_run_id: Object.prototype.hasOwnProperty.call(plan, 'run_id'),
  has_assignment_plan_id: Object.prototype.hasOwnProperty.call(assignment, 'plan_id'),
  has_assignment_run_id: Object.prototype.hasOwnProperty.call(assignment, 'run_id')
}));
"""
        )
        self.assertTrue(result["has_plan_id"])
        self.assertFalse(result["has_plan_run_id"])
        self.assertTrue(result["has_assignment_plan_id"])
        self.assertFalse(result["has_assignment_run_id"])

    def test_local_planner_top_level_output_contract_keys(self) -> None:
        result = _run_frontend_probe(
            """
const snapshot = context.createInitialSnapshot();
snapshot.orders = [{
  order_id: 9102,
  dispatch_date: '2026-04-22',
  delivery_address: '100 St Kilda Road, Melbourne VIC 3004',
  postcode: '3004',
  urgency: 'NORMAL',
  window_start: '09:00',
  window_end: '12:00',
  designated_driver_id: null,
  load_type: 'MIXED',
  pallet_count: 1,
  bag_count: 0,
  kg_count: 0
}];
const output = context.planDispatch(snapshot);
process.stdout.write(JSON.stringify({
  keys: Object.keys(output || {}).sort(),
  plan_has_run_id: Array.isArray(output.plans) && output.plans.some((item) => Object.prototype.hasOwnProperty.call(item, 'run_id')),
  assignment_has_run_id: Array.isArray(output.order_assignments) && output.order_assignments.some((item) => Object.prototype.hasOwnProperty.call(item, 'run_id'))
}));
"""
        )
        self.assertEqual(["exceptions", "order_assignments", "plans"], result["keys"])
        self.assertFalse(result["plan_has_run_id"])
        self.assertFalse(result["assignment_has_run_id"])

    def test_local_planner_prioritizes_preferred_zone_match(self) -> None:
        result = _run_frontend_probe(
            """
const snapshot = context.createInitialSnapshot();
snapshot.orders = [
  {
    order_id: 9201,
    dispatch_date: '2026-04-22',
    delivery_address: '328 Swanston Street, Melbourne VIC 3000',
    postcode: '3000',
    urgency: 'NORMAL',
    window_start: '08:00',
    window_end: '09:30',
    designated_driver_id: null,
    load_type: 'MIXED',
    pallet_count: 1,
    bag_count: 0,
    kg_count: 0
  },
  {
    order_id: 9202,
    dispatch_date: '2026-04-22',
    delivery_address: 'K Road, Werribee VIC 3030',
    postcode: '3030',
    urgency: 'NORMAL',
    window_start: '10:00',
    window_end: '13:30',
    designated_driver_id: null,
    load_type: 'MIXED',
    pallet_count: 1,
    bag_count: 0,
    kg_count: 0
  }
];
snapshot.drivers = [
  {
    driver_id: 1,
    name: 'Driver A',
    shift_start: '07:00',
    shift_end: '18:00',
    is_available: true,
    preferred_zone_codes: ['LOCAL'],
    start_location: 'Depot',
    end_location: 'Depot'
  },
  {
    driver_id: 2,
    name: 'Driver B',
    shift_start: '07:00',
    shift_end: '18:00',
    is_available: true,
    preferred_zone_codes: ['WEST'],
    start_location: 'Depot',
    end_location: 'Depot'
  }
];
snapshot.vehicles = [
  { vehicle_id: 1, vehicle_type: 'van', is_available: true, kg_capacity: 0, pallet_capacity: 6, tub_capacity: 12, trolley_capacity: 0, stillage_capacity: 0 },
  { vehicle_id: 2, vehicle_type: 'van', is_available: true, kg_capacity: 0, pallet_capacity: 6, tub_capacity: 12, trolley_capacity: 0, stillage_capacity: 0 }
];
const result = context.planDispatch(snapshot);
const byOrder = {};
for (const item of result.order_assignments || []) byOrder[String(item.order_id)] = item.driver_id;
process.stdout.write(JSON.stringify({
  local_driver: byOrder['9201'],
  west_driver: byOrder['9202']
}));
"""
        )
        self.assertEqual(1, result["local_driver"])
        self.assertEqual(2, result["west_driver"])

    def test_local_planner_prefers_same_zone_continuity_over_unused_balance(self) -> None:
        result = _run_frontend_probe(
            """
const snapshot = context.createInitialSnapshot();
snapshot.orders = [
  {
    order_id: 9301,
    dispatch_date: '2026-04-22',
    delivery_address: '328 Swanston Street, Melbourne VIC 3000',
    postcode: '3000',
    urgency: 'NORMAL',
    window_start: '08:00',
    window_end: '08:45',
    designated_driver_id: null,
    load_type: 'MIXED',
    pallet_count: 1,
    bag_count: 0,
    kg_count: 0
  },
  {
    order_id: 9302,
    dispatch_date: '2026-04-22',
    delivery_address: '100 St Kilda Road, Melbourne VIC 3004',
    postcode: '3004',
    urgency: 'NORMAL',
    window_start: '14:00',
    window_end: '14:45',
    designated_driver_id: null,
    load_type: 'MIXED',
    pallet_count: 1,
    bag_count: 0,
    kg_count: 0
  }
];
snapshot.drivers = [
  {
    driver_id: 1,
    name: 'Driver A',
    shift_start: '07:00',
    shift_end: '18:00',
    is_available: true,
    preferred_zone_codes: ['LOCAL'],
    historical_vehicle_ids: [1],
    start_location: 'Depot',
    end_location: 'Depot'
  },
  {
    driver_id: 2,
    name: 'Driver B',
    shift_start: '07:00',
    shift_end: '18:00',
    is_available: true,
    preferred_zone_codes: ['LOCAL'],
    start_location: 'Depot',
    end_location: 'Depot'
  }
];
snapshot.vehicles = [
  { vehicle_id: 1, vehicle_type: 'van', is_available: true, kg_capacity: 0, pallet_capacity: 6, tub_capacity: 12, trolley_capacity: 0, stillage_capacity: 0 },
  { vehicle_id: 2, vehicle_type: 'van', is_available: true, kg_capacity: 0, pallet_capacity: 6, tub_capacity: 12, trolley_capacity: 0, stillage_capacity: 0 }
];
const result = context.planDispatch(snapshot);
const byOrder = {};
for (const item of result.order_assignments || []) byOrder[String(item.order_id)] = item.driver_id;
process.stdout.write(JSON.stringify({
  first_driver: byOrder['9301'],
  second_driver: byOrder['9302']
}));
"""
        )
        self.assertEqual(1, result["first_driver"])
        self.assertEqual(1, result["second_driver"])


if __name__ == "__main__":
    unittest.main()
