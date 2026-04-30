# Findings

## Scope
This file captures baseline checks, architecture orientation, and consistency risks for the dispatch optimizer.

## 1) Skill Discovery Snapshot

### Checked locations
- `C:\Users\Albert Fang\.agents\skills`
- `C:\Users\Albert Fang\.codex\skills`

### Detected
- Available:
  - `planning-with-files`
  - `codebase-orientation`
  - `debugging-checklist`
  - `bug-repro-plan`
  - `unit-test-starter`
  - `integration-test-planner`
  - `api-contract-checker`
  - `readme-polish`
  - `ui-ux-pro-max`
  - `neat-freak`
- Missing:
  - `codebase-migrate`

### Session note
- Skills installed during an existing session may require a session restart before they become visible to runtime prompts.

## 2) Baseline Command Results

### Syntax
- `node --check frontend/app.js` -> pass
- `node --check frontend/overrides.js` -> pass

### Unit tests
- `python -m unittest discover -s tests -v` (via pinned Python 3.13 path) -> pass
- Current baseline: `Ran 79 tests`, `OK`

### CLI probe
- CLI execution can be environment-dependent in this shell chain.
- Tracked as runtime environment risk, not a confirmed business-logic regression.

## 3) Codebase Orientation Map

### Authoritative backend logic
- `dispatch_optimizer/*_core.py`:
  - `engine_core.py`
  - `assignment_core.py`
  - `run_generation_core.py`
  - `preprocess_core.py`
  - `routing_core.py`
  - `providers_core.py`
  - `models_core.py`

### Compatibility façades
- `dispatch_optimizer/*.py` wrapper re-exports for public import stability.

### Frontend layers
- Entry/layout: `frontend/index.html`
- Main orchestration + local preview planner: `frontend/app.js`
- UI helpers:
  - `frontend/modules/zone-utils.js`
  - `frontend/modules/driver-assignment-summary.js`
  - `frontend/modules/render-utils.js`
- Shim-only layer: `frontend/overrides.js`

### Tests and tooling
- Backend behavior: `tests/test_dispatch_engine.py`
- Frontend parity: `tests/test_frontend_behavior_parity.py`
- Governance/contract: `tests/test_project_governance.py`
- Tooling:
  - `tools/refresh_sample_master_data.py`
  - `tools/recycle.ps1`

## 4) README/Code Consistency Risks
1. Priority wording can drift if policy text in README is edited without matching tests.
2. Legacy terminology (`run`) can accidentally reappear in public-facing docs despite `plan_id` public contract.
3. Frontend local preview logic can diverge from backend authority if parity tests are relaxed.
4. Dashboard UI wiring can silently degrade if utility setters write only to form `.value` instead of text nodes.

## 5) Invariants Reconfirmed
- Backend `DispatchEngine` remains authoritative.
- Top-level output remains `plans / order_assignments / exceptions`.
- Public linkage remains `plan_id`.
- Zone-First policy remains intact.
- Hard constraints remain hard.
- Primary frontend business view remains `Driver -> Vehicle -> Orders`.
