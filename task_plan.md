# Dispatch Optimizer Optimization Plan (Phase 0–2 Only)

## Goal
Complete the preparation work for structural optimization (Phase 0/1/2), establish traceable planning and baselines, and do not modify business logic.

## Status
- Phase 0: complete
- Phase 1: complete
- Phase 2: complete
- Phase 3: complete
- Phase 4: complete
- Phase 5: complete
- Phase 6: complete
- Phase 7: complete

## Refactor Phases
1. Phase 0 — Planning files and invariants lock
2. Phase 1 — Baseline capture (syntax/tests/CLI probe)
3. Phase 2 — Codebase orientation and consistency risk map
4. Phase 3 — Safe backend cleanup (behavior-preserving)
5. Phase 4 — Safe frontend cleanup (behavior-preserving)
6. Phase 5 — Contract/parity protection
7. Phase 6 — README alignment
8. Phase 7 — Final optimization report

## Files to Inspect
- Backend/core: `dispatch_optimizer/engine_core.py`, `assignment_core.py`, `run_generation_core.py`, `preprocess_core.py`, `routing_core.py`, `providers_core.py`, `models_core.py`, `cli.py`
- Backend/facade: `dispatch_optimizer/*.py` (non-core)
- Frontend: `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`, `frontend/overrides.js`, `frontend/modules/*`
- Contracts/docs: `README.md`, `AGENTS.md`
- Tests: `tests/*`
- SQL: `sql/*`
- Samples/raw/tools: `examples/*`, `data/raw/*`, `tools/*`

## Invariants to Protect (Locked)
1. Backend `DispatchEngine` is authoritative result source.
2. Top-level output keys remain `plans / order_assignments / exceptions`.
3. Public output uses `plan_id`, not `run_id`.
4. `run_id` may exist internally, but not as public output contract field.
5. Keep Zone-First policy priority (2026-04-24):
   - hard constraints
   - urgent coverage
   - preferred-zone match
   - minimize driver-day zone spread
   - assignment coverage
   - same-day vehicle minimization
   - used drivers / balance / normal objective
6. Zone remains strong soft constraint, not hard constraint.
7. Cross-zone assignment remains allowed when needed.
8. Capacity/availability/designated-driver/hard-time remain hard constraints.
9. `plans` aggregation remains `dispatch_date + driver_id + vehicle_id`.
10. Every `order_assignments[*].plan_id` must reference an existing `plans[*].plan_id`.
11. Frontend main view remains business-facing: `Driver -> Vehicle -> Orders`.
12. Frontend main view should not expose run_id/stop sequence/ETA/departure.

## Test Commands
- `node --check frontend/app.js`
- `node --check frontend/overrides.js`
- `python -m unittest discover -s tests -v` (using available interpreter chain)
- `python -m dispatch_optimizer.cli examples/sample-dispatch-input.json` (probe; may fail by environment)

## Rollback Strategy (No Git Repository Present)
- Before Phase 3/4 edits, create timestamped backups in `tmp/backups/<YYYYMMDD-HHMMSS>/`.
- Keep changes in small passes and log each pass in `progress.md`.
- If a pass fails validation, restore only impacted files from latest backup set.
- Do not physically delete files; use `tools/recycle.ps1` when cleanup is needed.

## Errors Encountered
| Error | Where | Resolution/Next Step |
|---|---|---|
| Python interpreter exits with `-1073741790` for CLI probe | Phase 1 CLI run | Record as environment/runtime blocker; continue static/test baseline via existing unittest command chain. |
| `codebase-migrate` skill missing | Skill discovery | Record missing skill and provide local install path guidance. |
