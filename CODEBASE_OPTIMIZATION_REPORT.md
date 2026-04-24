# Codebase Optimization Report

## Summary
- Completed Phase 3 to Phase 7 under strict behavior-preserving gates.
- Focused on structure and maintainability improvements while preserving dispatch business behavior.
- Preserved authoritative backend contract and frontend business-facing primary view semantics.
- All required validation commands passed after each major phase.

## Files Changed

### Backend
- `dispatch_optimizer/assignment_core.py`
  - Extracted private helpers:
    - `_lock_stage_or_none`
    - `_build_greedy_sort_key`
    - `_append_explanation_messages`
    - `_build_driver_utilization_messages`
  - Refactor-only changes: reduced repeated stage-lock and explanation/sort-key boilerplate.
  - Safety: no scoring weights, stage order, or constraint semantics changed.

- `dispatch_optimizer/engine_core.py`
  - Extracted private helpers:
    - `_append_selected_candidate_output`
    - `_build_initial_aggregate_plan`
    - `_merge_aggregate_plan`
    - `_merge_load_summary`
    - `_remap_and_sort_assignments`
  - Refactor-only changes: reduced duplication in selected-candidate emission and aggregation/remap logic.
  - Safety: same aggregation key and output fields retained.

### Frontend
- `frontend/modules/render-utils.js` (new)
  - Added pure rendering helpers:
    - display lookups for driver/vehicle
    - display fallback resolvers
    - business explanation text normalizer
  - Safety: no planner/scoring logic; presentation helper only.

- `frontend/app.js`
  - Added module-aware delegation for rendering helpers via `DeliveryRenderUtils`.
  - Preserved in-file fallback behavior when module is unavailable.
  - Safety: no local planner priority/order/CSV semantics changed.

- `frontend/index.html`
  - Added script load for `modules/render-utils.js` before `app.js`.
  - Safety: no UI structure or business result semantics changed.

### Tests
- `tests/test_dispatch_engine.py`
  - Added behavior-protection tests:
    - `test_output_contract_keys_plan_links_and_unique_assigned_orders`
    - `test_plans_are_aggregated_by_dispatch_date_driver_vehicle`
  - Purpose: guard output contract and aggregation semantics.

- `tests/test_frontend_behavior_parity.py`
  - Added:
    - `test_local_planner_top_level_output_contract_keys`
  - Purpose: guard local planner top-level contract and no-public-run_id behavior.

### Documentation / Tracking
- `README.md`
  - Structural alignment updates only:
    - frontend module load sequence now includes `render-utils`
    - key-file section now documents `frontend/modules/render-utils.js`
  - No business-policy rewrite performed.

- `progress.md`
  - Updated with backups, pass-by-pass scope, and validation outcomes.

## Why Behavior Is Preserved
- No changes to:
  - scoring weights
  - objective priority/stage order
  - hard vs soft constraint boundaries
  - output JSON top-level shape
  - plan aggregation semantics
  - designated-driver/capacity/time hard constraints
- Changes were limited to helper extraction, code organization, and test/documentation guards.
- Validation ran after each major pass and remained green.

## Protected Invariants Checklist
- [x] Backend DispatchEngine remains authoritative.
- [x] Top-level output remains `plans / order_assignments / exceptions`.
- [x] Public output uses `plan_id`, not `run_id`.
- [x] Internal run/group objects remain internal-only semantics.
- [x] Zone-First policy order unchanged (2026-04-24).
- [x] Zone remains strong soft constraint, not hard.
- [x] Cross-zone assignment remains allowed when needed.
- [x] Capacity/availability/designated/hard-time remain hard constraints.
- [x] `plans` aggregation remains `dispatch_date + driver_id + vehicle_id`.
- [x] `order_assignments[*].plan_id` references existing `plans[*].plan_id`.
- [x] Frontend primary view remains `Driver -> Vehicle -> Orders`.
- [x] Frontend primary view does not expose run_id/ETA/stop/departure as primary business output.

## Test Results
Commands run after major passes:

```powershell
node --check frontend/app.js
node --check frontend/overrides.js
& 'C:\Program Files\MySQL\MySQL Workbench 8.0\swb\shell\lib\Python3.13\python.exe' -m unittest discover -s tests -v
```

Latest result:
- `node --check frontend/app.js` -> pass
- `node --check frontend/overrides.js` -> pass
- `python -m unittest discover -s tests -v` -> `Ran 75 tests ... OK (skipped=3)`

## Remaining Risks
- OR-Tools CP-SAT path is partially gated by environment (`skipped=3` tests where OR-Tools unavailable).
- `frontend/app.js` remains large despite modular improvement; further split is possible but should remain phase-gated.
- Existing README has historical sections with mixed legacy context; current pass only aligned structural changes.

## Decision Needed Items
- None introduced in this execution.
- Existing previously deferred decisions remain deferred and unmodified.

## Proposed Behavior Changes Not Applied
- No behavior changes were applied.
- No scoring/priority/constraint or contract changes were introduced.
