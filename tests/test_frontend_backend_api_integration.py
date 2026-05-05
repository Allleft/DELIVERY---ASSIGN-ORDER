from __future__ import annotations

import json
import subprocess
import unittest


def _run_frontend_probe(script_body: str) -> dict:
    script = f"""
const fs = require('fs');
const vm = require('vm');
const elements = {{}};
function makeElement() {{
  return {{
    addEventListener: () => {{}},
    querySelector: () => null,
    querySelectorAll: () => [],
    closest: () => null,
    disabled: false,
    value: '',
    textContent: '',
    innerHTML: '',
    className: '',
    dataset: {{}},
    classList: {{ add: () => {{}}, remove: () => {{}}, toggle: () => {{}} }},
  }};
}}
const context = {{ console }};
context.document = {{
  addEventListener: () => {{}},
  createElement: () => ({{ click: () => {{}} }}),
  body: {{ appendChild: () => {{}}, removeChild: () => {{}}, classList: {{ toggle: () => {{}} }} }},
  getElementById: (id) => {{
    if (!elements[id]) elements[id] = makeElement();
    return elements[id];
  }},
}};
context.URL = {{ createObjectURL: () => '', revokeObjectURL: () => {{}} }};
context.Blob = function Blob() {{}};
context.fetch = async () => {{ throw new Error('fetch unavailable'); }};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/modules/zone-utils.js', 'utf8'), context, {{ filename: 'frontend/modules/zone-utils.js' }});
vm.runInContext(fs.readFileSync('frontend/modules/driver-assignment-summary.js', 'utf8'), context, {{ filename: 'frontend/modules/driver-assignment-summary.js' }});
vm.runInContext(fs.readFileSync('frontend/modules/render-utils.js', 'utf8'), context, {{ filename: 'frontend/modules/render-utils.js' }});
vm.runInContext(fs.readFileSync('frontend/modules/backend-api.js', 'utf8'), context, {{ filename: 'frontend/modules/backend-api.js' }});
vm.runInContext(fs.readFileSync('frontend/app.js', 'utf8'), context, {{ filename: 'frontend/app.js' }});
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


class FrontendBackendApiIntegrationTest(unittest.TestCase):
    def test_backend_api_module_exposes_required_functions(self) -> None:
        result = _run_frontend_probe(
            """
const api = context.OfficeDispatchBackendApi || {};
process.stdout.write(JSON.stringify({
  has_createBatch: typeof api.createBatch === 'function',
  has_saveBatchOrders: typeof api.saveBatchOrders === 'function',
  has_saveDrivers: typeof api.saveDrivers === 'function',
  has_listDrivers: typeof api.listDrivers === 'function',
  has_saveVehicles: typeof api.saveVehicles === 'function',
  has_listVehicles: typeof api.listVehicles === 'function',
  has_getBatchResult: typeof api.getBatchResult === 'function',
  has_generateBatchPlan: typeof api.generateBatchPlan === 'function',
  has_updateManualAssignment: typeof api.updateManualAssignment === 'function',
  has_getBatch: typeof api.getBatch === 'function',
  has_listBatches: typeof api.listBatches === 'function',
  has_listBatchOrders: typeof api.listBatchOrders === 'function',
  default_base: api.DEFAULT_BASE_URL || null
}));
"""
        )
        self.assertTrue(result["has_createBatch"])
        self.assertTrue(result["has_saveBatchOrders"])
        self.assertTrue(result["has_saveDrivers"])
        self.assertTrue(result["has_listDrivers"])
        self.assertTrue(result["has_saveVehicles"])
        self.assertTrue(result["has_listVehicles"])
        self.assertTrue(result["has_getBatchResult"])
        self.assertTrue(result["has_generateBatchPlan"])
        self.assertTrue(result["has_updateManualAssignment"])
        self.assertTrue(result["has_getBatch"])
        self.assertTrue(result["has_listBatches"])
        self.assertTrue(result["has_listBatchOrders"])
        self.assertEqual("http://127.0.0.1:8000", result["default_base"])

    def test_load_selected_saved_batch_restores_snapshot_and_result(self) -> None:
        result = _run_frontend_probe(
            """
(async () => {
  const calls = [];
  let capturedSnapshot = null;
  let renderedResult = null;
  let bannerMessage = '';
  context.bootstrap();
  context.applyUiMode = () => {};
  context.renderInputSummaryPanel = () => {};
  context.renderReviewDashboard = (result) => { renderedResult = result; };
  context.applySnapshotToState = (snapshot) => { capturedSnapshot = snapshot; };
  context.banner = (msg) => { bannerMessage = String(msg || ''); };
  const selectNode = context.document.getElementById('savedBatchSelect');
  selectNode.value = '42';
  context.OfficeDispatchBackendApi = {
    getBatch: async (batchId) => {
      calls.push(`getBatch:${batchId}`);
      return { batch_id: Number(batchId), generated_at: '2026-05-05T09:00:00' };
    },
    listBatchOrders: async (batchId) => {
      calls.push(`listBatchOrders:${batchId}`);
      return [{ order_id: 5001, dispatch_date: '2026-05-05', delivery_address: 'A', postcode: '3000', zone_code: 'LOCAL', urgency: 'NORMAL', window_start: '08:00', window_end: '10:00' }];
    },
    listDrivers: async () => {
      calls.push('listDrivers');
      return [{ driver_id: 1, shift_start: '07:00', shift_end: '17:00', is_available: true, start_location: 'Depot', end_location: 'Depot', preferred_zone_codes: [] }];
    },
    listVehicles: async () => {
      calls.push('listVehicles');
      return [{ vehicle_id: 2, vehicle_type: 'van', is_available: true, kg_capacity: 0, pallet_capacity: 1, tub_capacity: 0, trolley_capacity: 0, stillage_capacity: 0 }];
    },
    getBatchResult: async (batchId) => {
      calls.push(`getBatchResult:${batchId}`);
      return { plans: [{ plan_id: 'PLAN-SAVED' }], order_assignments: [{ order_id: 5001, plan_id: 'PLAN-SAVED' }], exceptions: [] };
    }
  };
  await context.handleLoadSelectedBatch();
  process.stdout.write(JSON.stringify({
    calls,
    restored_orders: Array.isArray(capturedSnapshot?.orders) ? capturedSnapshot.orders.length : -1,
    restored_drivers: Array.isArray(capturedSnapshot?.drivers) ? capturedSnapshot.drivers.length : -1,
    restored_vehicles: Array.isArray(capturedSnapshot?.vehicles) ? capturedSnapshot.vehicles.length : -1,
    restored_plan_id: renderedResult?.plans?.[0]?.plan_id || null,
    banner_mentions_loaded: bannerMessage.toLowerCase().includes('loaded saved batch')
  }));
})();
"""
        )
        self.assertEqual(
            [
                "getBatch:42",
                "listBatchOrders:42",
                "listDrivers",
                "listVehicles",
                "getBatchResult:42",
            ],
            result["calls"],
        )
        self.assertEqual(1, result["restored_orders"])
        self.assertEqual(1, result["restored_drivers"])
        self.assertEqual(1, result["restored_vehicles"])
        self.assertEqual("PLAN-SAVED", result["restored_plan_id"])
        self.assertTrue(result["banner_mentions_loaded"])

    def test_generate_plan_backend_success_syncs_drivers_vehicles_before_generate(self) -> None:
        result = _run_frontend_probe(
            """
(async () => {
  const calls = [];
  let renderedResult = null;
  context.bootstrap();
  context.applySnapshotToState(context.createSampleSnapshot());
  context.validateViewModel = () => ({ errors: [], warnings: [], rowErrors: { orders: new Set(), drivers: new Set(), vehicles: new Set() } });
  context.renderValidationPanel = () => {};
  context.renderWorkbench = () => {};
  context.renderSnapshotEditor = () => {};
  context.applyUiMode = () => {};
  context.renderReviewDashboard = (result) => { renderedResult = result; };
  context.renderInputSummaryPanel = () => {};
  context.banner = () => {};
  context.OfficeDispatchBackendApi = {
    createBatch: async () => { calls.push('createBatch'); return { batch_id: 501 }; },
    saveDrivers: async (drivers) => { calls.push(`saveDrivers:${Array.isArray(drivers) ? drivers.length : -1}`); return drivers; },
    saveVehicles: async (vehicles) => { calls.push(`saveVehicles:${Array.isArray(vehicles) ? vehicles.length : -1}`); return vehicles; },
    saveBatchOrders: async (batchId, orders) => { calls.push(`saveBatchOrders:${batchId}:${Array.isArray(orders) ? orders.length : -1}`); return orders; },
    generateBatchPlan: async (batchId) => {
      calls.push(`generateBatchPlan:${batchId}`);
      return { plans: [{ plan_id: 'PLAN-BACKEND' }], order_assignments: [{ order_id: 1, plan_id: 'PLAN-BACKEND' }], exceptions: [] };
    }
  };
  await context.handleRunPlanner();
  process.stdout.write(JSON.stringify({
    calls,
    plan_id: renderedResult?.plans?.[0]?.plan_id || null,
    result_keys: Object.keys(renderedResult || {}).sort()
  }));
})();
"""
        )
        self.assertEqual("PLAN-BACKEND", result["plan_id"])
        self.assertEqual(["exceptions", "order_assignments", "plans"], result["result_keys"])
        self.assertGreaterEqual(len(result["calls"]), 5)
        self.assertEqual("createBatch", result["calls"][0])
        self.assertTrue(str(result["calls"][1]).startswith("saveDrivers:"))
        self.assertTrue(str(result["calls"][2]).startswith("saveVehicles:"))
        self.assertTrue(str(result["calls"][3]).startswith("saveBatchOrders:"))
        self.assertTrue(str(result["calls"][4]).startswith("generateBatchPlan:"))

    def test_generate_plan_validation_failure_keeps_busy_state_false(self) -> None:
        result = _run_frontend_probe(
            """
(async () => {
  let validateCalls = 0;
  const calls = [];
  const runBtn = context.document.getElementById('runPlannerBtn');
  const regenBtn = context.document.getElementById('regeneratePlanBtn');
  const summaryRegenBtn = context.document.getElementById('summaryRegenerateBtn');
  runBtn.textContent = 'Generate Plan';
  regenBtn.textContent = 'Regenerate Plan';
  summaryRegenBtn.textContent = 'Regenerate Plan';
  context.bootstrap();
  context.applySnapshotToState(context.createSampleSnapshot());
  context.validateViewModel = () => {
    validateCalls += 1;
    return { errors: ['invalid'], warnings: [], rowErrors: { orders: new Set(), drivers: new Set(), vehicles: new Set() } };
  };
  context.renderValidationPanel = () => {};
  context.renderWorkbench = () => {};
  context.renderSnapshotEditor = () => {};
  context.banner = () => {};
  context.OfficeDispatchBackendApi = {
    createBatch: async () => { calls.push('createBatch'); return { batch_id: 1 }; },
    saveDrivers: async () => { calls.push('saveDrivers'); return []; },
    saveVehicles: async () => { calls.push('saveVehicles'); return []; },
    saveBatchOrders: async () => { calls.push('saveBatchOrders'); return []; },
    generateBatchPlan: async () => { calls.push('generateBatchPlan'); return { plans: [], order_assignments: [], exceptions: [] }; }
  };
  await context.handleRunPlanner();
  await context.handleRunPlanner();
  process.stdout.write(JSON.stringify({
    validate_calls: validateCalls,
    backend_calls: calls.length,
    run_disabled: !!runBtn.disabled,
    regen_disabled: !!regenBtn.disabled,
    summary_regen_disabled: !!summaryRegenBtn.disabled,
    run_text: runBtn.textContent
  }));
})();
"""
        )
        self.assertEqual(2, result["validate_calls"])
        self.assertEqual(0, result["backend_calls"])
        self.assertFalse(result["run_disabled"])
        self.assertFalse(result["regen_disabled"])
        self.assertFalse(result["summary_regen_disabled"])
        self.assertEqual("Generate Plan", result["run_text"])

    def test_generate_plan_prevents_duplicate_submission_while_busy(self) -> None:
        result = _run_frontend_probe(
            """
(async () => {
  const calls = [];
  const runBtn = context.document.getElementById('runPlannerBtn');
  const regenBtn = context.document.getElementById('regeneratePlanBtn');
  const summaryRegenBtn = context.document.getElementById('summaryRegenerateBtn');
  runBtn.textContent = 'Generate Plan';
  regenBtn.textContent = 'Regenerate Plan';
  summaryRegenBtn.textContent = 'Regenerate Plan';
  context.bootstrap();
  context.applySnapshotToState(context.createSampleSnapshot());
  context.validateViewModel = () => ({ errors: [], warnings: [], rowErrors: { orders: new Set(), drivers: new Set(), vehicles: new Set() } });
  context.renderValidationPanel = () => {};
  context.renderWorkbench = () => {};
  context.renderSnapshotEditor = () => {};
  context.applyUiMode = () => {};
  context.renderReviewDashboard = () => {};
  context.renderInputSummaryPanel = () => {};
  context.banner = () => {};
  let releaseGenerate = null;
  const generateGate = new Promise((resolve) => { releaseGenerate = resolve; });
  context.OfficeDispatchBackendApi = {
    createBatch: async () => { calls.push('createBatch'); return { batch_id: 801 }; },
    saveDrivers: async () => { calls.push('saveDrivers'); return []; },
    saveVehicles: async () => { calls.push('saveVehicles'); return []; },
    saveBatchOrders: async () => { calls.push('saveBatchOrders'); return []; },
    generateBatchPlan: async () => {
      calls.push('generateBatchPlan');
      await generateGate;
      return { plans: [{ plan_id: 'PLAN-BUSY' }], order_assignments: [], exceptions: [] };
    }
  };

  const firstRun = context.handleRunPlanner();
  await Promise.resolve();
  await Promise.resolve();
  const secondRun = context.handleRunPlanner();
  await Promise.resolve();

  const during = {
    run_disabled: !!runBtn.disabled,
    regen_disabled: !!regenBtn.disabled,
    summary_regen_disabled: !!summaryRegenBtn.disabled,
    run_text: runBtn.textContent,
    regen_text: regenBtn.textContent,
    summary_regen_text: summaryRegenBtn.textContent,
  };

  releaseGenerate();
  await firstRun;
  await secondRun;

  process.stdout.write(JSON.stringify({
    calls,
    during,
    after: {
      run_disabled: !!runBtn.disabled,
      regen_disabled: !!regenBtn.disabled,
      summary_regen_disabled: !!summaryRegenBtn.disabled,
      run_text: runBtn.textContent,
      regen_text: regenBtn.textContent,
      summary_regen_text: summaryRegenBtn.textContent,
    }
  }));
})();
"""
        )
        self.assertEqual(1, sum(1 for item in result["calls"] if item == "createBatch"))
        self.assertEqual(1, sum(1 for item in result["calls"] if item == "generateBatchPlan"))
        self.assertTrue(result["during"]["run_disabled"])
        self.assertTrue(result["during"]["regen_disabled"])
        self.assertTrue(result["during"]["summary_regen_disabled"])
        self.assertEqual("Generating...", result["during"]["run_text"])
        self.assertEqual("Generating...", result["during"]["regen_text"])
        self.assertEqual("Generating...", result["during"]["summary_regen_text"])
        self.assertFalse(result["after"]["run_disabled"])
        self.assertFalse(result["after"]["regen_disabled"])
        self.assertFalse(result["after"]["summary_regen_disabled"])
        self.assertEqual("Generate Plan", result["after"]["run_text"])
        self.assertEqual("Regenerate Plan", result["after"]["regen_text"])
        self.assertEqual("Regenerate Plan", result["after"]["summary_regen_text"])

    def test_generate_plan_falls_back_to_local_when_backend_fails(self) -> None:
        result = _run_frontend_probe(
            """
(async () => {
  let bannerMessage = '';
  let bannerTone = '';
  let renderedResult = null;
  context.bootstrap();
  context.applySnapshotToState(context.createSampleSnapshot());
  context.validateViewModel = () => ({ errors: [], warnings: [], rowErrors: { orders: new Set(), drivers: new Set(), vehicles: new Set() } });
  context.renderValidationPanel = () => {};
  context.renderWorkbench = () => {};
  context.renderSnapshotEditor = () => {};
  context.applyUiMode = () => {};
  context.renderReviewDashboard = (result) => { renderedResult = result; };
  context.renderInputSummaryPanel = () => {};
  context.OfficeDispatchBackendApi = {
    createBatch: async () => ({ batch_id: 600 }),
    saveDrivers: async () => { throw new Error('No active drivers'); },
    saveVehicles: async () => [],
    saveBatchOrders: async () => [],
    generateBatchPlan: async () => ({ plans: [], order_assignments: [], exceptions: [] })
  };
  context.planDispatch = () => ({ plans: [{ plan_id: 'PLAN-LOCAL' }], order_assignments: [], exceptions: [] });
  context.banner = (msg, tone) => { bannerMessage = String(msg || ''); bannerTone = String(tone || ''); };
  await context.handleRunPlanner();
  process.stdout.write(JSON.stringify({
    used_fallback_result: Array.isArray(renderedResult?.plans) && renderedResult.plans[0]?.plan_id === 'PLAN-LOCAL',
    message_mentions_fallback: bannerMessage.toLowerCase().includes('falling back to local planner'),
    banner_tone: bannerTone,
    result_keys: Object.keys(renderedResult || {}).sort(),
    run_disabled: !!context.document.getElementById('runPlannerBtn').disabled,
    run_text: context.document.getElementById('runPlannerBtn').textContent,
    regen_disabled: !!context.document.getElementById('regeneratePlanBtn').disabled,
    regen_text: context.document.getElementById('regeneratePlanBtn').textContent
  }));
})();
"""
        )
        self.assertTrue(result["used_fallback_result"])
        self.assertTrue(result["message_mentions_fallback"])
        self.assertEqual("info", result["banner_tone"])
        self.assertEqual(["exceptions", "order_assignments", "plans"], result["result_keys"])
        self.assertFalse(result["run_disabled"])
        self.assertFalse(result["regen_disabled"])
        self.assertEqual("Generate Plan", result["run_text"])
        self.assertEqual("Regenerate Plan", result["regen_text"])

    def test_manual_reassign_success_uses_backend_batch_and_replaces_result(self) -> None:
        result = _run_frontend_probe(
            """
(async () => {
  const calls = [];
  let renderedResult = null;
  let bannerMessage = '';
  context.bootstrap();
  context.applySnapshotToState(context.createSampleSnapshot());
  context.validateViewModel = () => ({ errors: [], warnings: [], rowErrors: { orders: new Set(), drivers: new Set(), vehicles: new Set() } });
  context.renderValidationPanel = () => {};
  context.renderWorkbench = () => {};
  context.renderSnapshotEditor = () => {};
  context.applyUiMode = () => {};
  context.renderReviewDashboard = (result) => { renderedResult = result; };
  context.renderReviewDriverCards = () => {};
  context.renderInputSummaryPanel = () => {};
  context.banner = (msg) => { bannerMessage = String(msg || ''); };
  context.OfficeDispatchBackendApi = {
    createBatch: async () => ({ batch_id: 903 }),
    saveDrivers: async () => [],
    saveVehicles: async () => [],
    saveBatchOrders: async () => [],
    generateBatchPlan: async () => ({
      plans: [{ plan_id: 'PLAN-A' }],
      order_assignments: [{ order_id: 2001, plan_id: 'PLAN-A', driver_id: 1, vehicle_id: 101, status: 'ASSIGNED', assignment_source: 'AUTO' }],
      exceptions: []
    }),
    updateManualAssignment: async (batchId, orderId, payload) => {
      calls.push(`update:${batchId}:${orderId}:${payload.driver_id}:${payload.vehicle_id}`);
      return {
        plans: [{ plan_id: 'PLAN-B' }],
        order_assignments: [{ order_id: 2001, plan_id: 'PLAN-B', driver_id: payload.driver_id, vehicle_id: payload.vehicle_id, status: 'MANUALLY_ASSIGNED', assignment_source: 'MANUAL' }],
        exceptions: []
      };
    }
  };
  await context.handleRunPlanner();
  const ok = await context.saveManualAssignment('2001', '2', '9');
  process.stdout.write(JSON.stringify({
    ok,
    calls,
    plan_id: renderedResult?.plans?.[0]?.plan_id || null,
    assignment_source: renderedResult?.order_assignments?.[0]?.assignment_source || null,
    status: renderedResult?.order_assignments?.[0]?.status || null,
    result_keys: Object.keys(renderedResult || {}).sort(),
    banner_mentions_success: bannerMessage.toLowerCase().includes('manually reassigned')
  }));
})();
"""
        )
        self.assertTrue(result["ok"])
        self.assertEqual(["update:903:2001:2:9"], result["calls"])
        self.assertEqual("PLAN-B", result["plan_id"])
        self.assertEqual("MANUAL", result["assignment_source"])
        self.assertEqual("MANUALLY_ASSIGNED", result["status"])
        self.assertEqual(["exceptions", "order_assignments", "plans"], result["result_keys"])
        self.assertTrue(result["banner_mentions_success"])

    def test_manual_reassign_failure_keeps_result_and_does_not_fallback(self) -> None:
        result = _run_frontend_probe(
            """
(async () => {
  let renderedResult = null;
  let fallbackUsed = false;
  let bannerMessage = '';
  context.bootstrap();
  context.applySnapshotToState(context.createSampleSnapshot());
  context.validateViewModel = () => ({ errors: [], warnings: [], rowErrors: { orders: new Set(), drivers: new Set(), vehicles: new Set() } });
  context.renderValidationPanel = () => {};
  context.renderWorkbench = () => {};
  context.renderSnapshotEditor = () => {};
  context.applyUiMode = () => {};
  context.renderReviewDashboard = (result) => { renderedResult = result; };
  context.renderReviewDriverCards = () => {};
  context.renderInputSummaryPanel = () => {};
  context.planDispatch = () => { fallbackUsed = true; return { plans: [{ plan_id: 'PLAN-LOCAL' }], order_assignments: [], exceptions: [] }; };
  context.banner = (msg) => { bannerMessage = String(msg || ''); };
  context.OfficeDispatchBackendApi = {
    createBatch: async () => ({ batch_id: 904 }),
    saveDrivers: async () => [],
    saveVehicles: async () => [],
    saveBatchOrders: async () => [],
    generateBatchPlan: async () => ({
      plans: [{ plan_id: 'PLAN-A' }],
      order_assignments: [{ order_id: 2001, plan_id: 'PLAN-A', driver_id: 1, vehicle_id: 101, status: 'ASSIGNED', assignment_source: 'AUTO' }],
      exceptions: []
    }),
    updateManualAssignment: async () => { throw new Error('LOCKED batch'); }
  };
  await context.handleRunPlanner();
  const beforePlanId = renderedResult?.plans?.[0]?.plan_id || null;
  const ok = await context.saveManualAssignment('2001', '2', '9');
  process.stdout.write(JSON.stringify({
    ok,
    before_plan_id: beforePlanId,
    after_plan_id: renderedResult?.plans?.[0]?.plan_id || null,
    fallback_used: fallbackUsed,
    banner_mentions_failure: bannerMessage.toLowerCase().includes('manual reassignment failed')
  }));
})();
"""
        )
        self.assertFalse(result["ok"])
        self.assertEqual("PLAN-A", result["before_plan_id"])
        self.assertEqual("PLAN-A", result["after_plan_id"])
        self.assertFalse(result["fallback_used"])
        self.assertTrue(result["banner_mentions_failure"])


if __name__ == "__main__":
    unittest.main()
