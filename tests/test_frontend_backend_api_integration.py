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
  has_generateBatchPlan: typeof api.generateBatchPlan === 'function',
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
        self.assertTrue(result["has_generateBatchPlan"])
        self.assertTrue(result["has_getBatch"])
        self.assertTrue(result["has_listBatches"])
        self.assertTrue(result["has_listBatchOrders"])
        self.assertEqual("http://127.0.0.1:8000", result["default_base"])

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
    result_keys: Object.keys(renderedResult || {}).sort()
  }));
})();
"""
        )
        self.assertTrue(result["used_fallback_result"])
        self.assertTrue(result["message_mentions_fallback"])
        self.assertEqual("info", result["banner_tone"])
        self.assertEqual(["exceptions", "order_assignments", "plans"], result["result_keys"])


if __name__ == "__main__":
    unittest.main()
