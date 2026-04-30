# Dispatch Optimizer Maintenance Plan (Completed Baseline + Guardrails)

## Goal
Keep structure, documentation, and governance aligned with the implemented system while preserving dispatch business behavior and public contracts.

## Current Status
- Phase 0: complete (planning artifacts)
- Phase 1: complete (baseline capture)
- Phase 2: complete (codebase orientation)
- Phase 3: complete (backend behavior-preserving cleanup)
- Phase 4: complete (frontend behavior-preserving cleanup)
- Phase 5: complete (contract/parity protection tests)
- Phase 6: complete (README alignment)
- Phase 7: complete (final optimization reporting)

## Locked Invariants
1. Backend `DispatchEngine` remains the authoritative result source.
2. Top-level output keys remain `plans / order_assignments / exceptions`.
3. Public linkage uses `plan_id` (no public `run_id` contract).
4. Zone-First policy order remains unchanged.
5. Zone remains a strong soft constraint, not a hard constraint.
6. Cross-zone fallback remains allowed when needed.
7. Capacity, availability, designated-driver, and hard-time constraints remain hard constraints.
8. `plans` aggregation remains `dispatch_date + driver_id + vehicle_id`.
9. Every `order_assignments[*].plan_id` must map to an existing `plans[*].plan_id`.
10. Frontend primary business view remains `Driver -> Vehicle -> Orders`.
11. Frontend primary business view must not expose run/ETA/stop/departure as primary output.

## Files of Interest
- Backend core: `dispatch_optimizer/*_core.py`
- Backend façade: `dispatch_optimizer/*.py`
- Frontend: `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`, `frontend/overrides.js`, `frontend/modules/*`
- Contracts/docs: `README.md`, `AGENTS.md`, `docs/*`
- Tests: `tests/*`
- Data/tooling: `examples/*`, `data/raw/*`, `tools/*`, `sql/*`

## Validation Commands
- `node --check frontend/app.js`
- `node --check frontend/overrides.js`
- `python -m unittest discover -s tests -v`  
  (or the pinned interpreter chain used in this workspace)

## Backup and Rollback Strategy
- Before major refactor passes, create timestamped backups in `tmp/backups/<YYYYMMDD-HHMMSS>/`.
- Keep changes in small passes and log each pass in `progress.md`.
- If a pass fails validation, restore only impacted files from the latest backup set.
- Do not physically delete files; use `tools/recycle.ps1` when cleanup is required.
