from __future__ import annotations

import unittest
from pathlib import Path


class ProjectGovernanceTest(unittest.TestCase):
    def test_readme_contains_required_contract_sections(self) -> None:
        text = Path("README.md").read_text(encoding="utf-8")
        markers = [
            "## 1. Project Overview",
            "## 2. Project Main Flow",
            "## 3. Directory Structure",
            "## 4. Key Files / Modules",
            "## 5. Data Sources and Master Data Flow",
            "## 6. Frontend Notes",
            "## 7. Dispatch Algorithm Notes",
            "## 8. Configuration and Run Commands",
            "## 9. Important Rules and Constraints",
            "## 10. Known Boundaries / Notes",
            "`plans / order_assignments / exceptions`",
            "postcode + zone_code",
            "preferred_zone_codes",
            "POSTCODE_NOT_MAPPED",
            "`service_minutes` has been removed from input",
            "Google Routes API",
            "cache first -> Google Routes -> Haversine fallback",
            "vehicle_switch_penalty",
            "Driver Assignment Summary",
            "Assignment Groups (Secondary)",
            "Driver -> Vehicle -> Orders",
            "`tools/refresh_sample_master_data.py` only updates `drivers` and `vehicles`",
            "front page starts with empty `orders`",
            "compatible with both flat config top-level keys and nested `config`",
            "Most `dispatch_optimizer/*.py` are façade files; implementation is in `*_core.py`",
            "`frontend/overrides.js`",
            "tools/recycle.ps1",
            "trip grouping + assignment",
            "hard constraints -> urgent coverage -> preferred-zone match -> minimize driver-day zone spread -> same-day vehicle minimization -> assignment coverage -> used drivers / balance / normal objective",
            "zone_mismatch_penalty=2500",
            "DRIVER_UNUSED_NO_FEASIBLE_CANDIDATE",
            "Plan ID Migration (2026-04-23)",
            "`order_assignments[*]` is linked by the same `plan_id`",
            "detailed routing is no longer the primary output",
        ]
        for marker in markers:
            self.assertIn(marker, text)

    def test_recycle_script_uses_recycle_bin(self) -> None:
        script = Path("tools/recycle.ps1")
        self.assertTrue(script.exists())
        content = script.read_text(encoding="utf-8")
        self.assertIn("SendToRecycleBin", content)

    def test_frontend_loads_consistency_overrides(self) -> None:
        html = Path("frontend/index.html").read_text(encoding="utf-8")
        self.assertIn("modules/zone-utils.js", html)
        self.assertIn("modules/driver-assignment-summary.js", html)
        self.assertIn("overrides.js", html)
        self.assertIn("postcode", html)
        self.assertIn("Driver Assignment Summary", html)
        self.assertIn("Assignment Groups (Secondary)", html)
        self.assertNotIn("zone_id</th>", html.lower())

    def test_frontend_script_load_order(self) -> None:
        html = Path("frontend/index.html").read_text(encoding="utf-8")
        zone_idx = html.find("modules/zone-utils.js")
        summary_idx = html.find("modules/driver-assignment-summary.js")
        app_idx = html.find("app.js?v=")
        overrides_idx = html.find("overrides.js?v=")
        self.assertGreaterEqual(zone_idx, 0)
        self.assertGreaterEqual(summary_idx, 0)
        self.assertGreaterEqual(app_idx, 0)
        self.assertGreaterEqual(overrides_idx, 0)
        self.assertLess(zone_idx, summary_idx)
        self.assertLess(summary_idx, app_idx)
        self.assertLess(app_idx, overrides_idx)

    def test_overrides_is_shim_only(self) -> None:
        text = Path("frontend/overrides.js").read_text(encoding="utf-8")
        self.assertIn("__deliveryFrontendOverrideShim", text)
        forbidden = [
            "function handleRunPlanner(",
            "function normalizeSnapshotShape(",
            "function snapshotToViewModel(",
            "function viewModelToSnapshot(",
            "function renderAssignments(",
        ]
        for token in forbidden:
            self.assertNotIn(token, text)

    def test_repo_agents_guardrails_exist(self) -> None:
        agents = Path("AGENTS.md")
        self.assertTrue(agents.exists())
        text = agents.read_text(encoding="utf-8")
        self.assertIn("plans / order_assignments / exceptions", text)
        self.assertIn("postcode + zone_code", text)
        self.assertIn("Audit first, then modify", text)
        self.assertIn("README.md", text)
        self.assertIn("tools/recycle.ps1", text)

    def test_providers_module_keeps_facade_reexport(self) -> None:
        providers = Path("dispatch_optimizer/providers.py")
        self.assertTrue(providers.exists())
        text = providers.read_text(encoding="utf-8")
        self.assertIn("providers_core", text)
        self.assertIn("re-exports", text)

    def test_assignment_module_keeps_facade_reexport(self) -> None:
        assignment = Path("dispatch_optimizer/assignment.py")
        self.assertTrue(assignment.exists())
        text = assignment.read_text(encoding="utf-8")
        self.assertIn("assignment_core", text)
        self.assertIn("re-exports", text)

    def test_routing_module_keeps_facade_reexport(self) -> None:
        routing = Path("dispatch_optimizer/routing.py")
        self.assertTrue(routing.exists())
        text = routing.read_text(encoding="utf-8")
        self.assertIn("routing_core", text)
        self.assertIn("re-exports", text)

    def test_engine_module_keeps_facade_reexport(self) -> None:
        engine = Path("dispatch_optimizer/engine.py")
        self.assertTrue(engine.exists())
        text = engine.read_text(encoding="utf-8")
        self.assertIn("engine_core", text)
        self.assertIn("re-exports", text)

    def test_run_generation_module_keeps_facade_reexport(self) -> None:
        run_generation = Path("dispatch_optimizer/run_generation.py")
        self.assertTrue(run_generation.exists())
        text = run_generation.read_text(encoding="utf-8")
        self.assertIn("run_generation_core", text)
        self.assertIn("re-exports", text)

    def test_preprocess_module_keeps_facade_reexport(self) -> None:
        preprocess = Path("dispatch_optimizer/preprocess.py")
        self.assertTrue(preprocess.exists())
        text = preprocess.read_text(encoding="utf-8")
        self.assertIn("preprocess_core", text)
        self.assertIn("re-exports", text)

    def test_models_module_keeps_facade_reexport(self) -> None:
        models = Path("dispatch_optimizer/models.py")
        self.assertTrue(models.exists())
        text = models.read_text(encoding="utf-8")
        self.assertIn("models_core", text)
        self.assertIn("re-exports", text)

    def test_backend_core_split_files_exist(self) -> None:
        core_files = [
            "dispatch_optimizer/providers_core.py",
            "dispatch_optimizer/assignment_core.py",
            "dispatch_optimizer/routing_core.py",
            "dispatch_optimizer/engine_core.py",
            "dispatch_optimizer/run_generation_core.py",
            "dispatch_optimizer/preprocess_core.py",
            "dispatch_optimizer/models_core.py",
        ]
        for path in core_files:
            self.assertTrue(Path(path).exists(), msg=f"missing split core file: {path}")


if __name__ == "__main__":
    unittest.main()
