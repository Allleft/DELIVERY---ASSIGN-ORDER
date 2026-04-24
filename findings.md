# Findings (Phase 0–2)

## 1) Skill Discovery (Requested Skills)

### Checked Locations
- `C:\Users\Albert Fang\.agents\skills`
- `C:\Users\Albert Fang\.codex\skills`
- Specific `SKILL.md` paths under `.agents/skills`

### Detected
- ✅ `planning-with-files`
- ✅ `codebase-orientation`
- ❌ `codebase-migrate` (not found at `C:\Users\Albert Fang\.agents\skills\codebase-migrate\SKILL.md`)
- ✅ `debugging-checklist`
- ✅ `bug-repro-plan`
- ✅ `unit-test-starter`
- ✅ `integration-test-planner`
- ✅ `api-contract-checker`
- ✅ `readme-polish`
- ✅ `ui-ux-pro-max`

### Availability Note
- `.agents/skills` has the requested skill folders (except `codebase-migrate`).
- `.codex/skills` currently shows only a subset; session-visible list may differ from `.agents/skills`.

## 2) Baseline Capture Results

### Syntax Checks
- `node --check frontend/app.js` → pass
- `node --check frontend/overrides.js` → pass

### Unit Test Baseline
- Command: `python -m unittest discover -s tests -v` (via available interpreter chain)
- Result: **72 passed, 3 skipped, 0 failed**
- Relevant suites present:
  - backend dispatch behavior
  - frontend behavior parity
  - API/governance guards
  - sample refresh guards
  - zone mapping guards

### CLI Sample Probe
- Command: `python -m dispatch_optimizer.cli examples/sample-dispatch-input.json`
- Result: process exits with `LASTEXIT=-1073741790` (no stdout/stderr payload in this environment)
- Classification: **environment/runtime issue**, not yet a business-logic regression signal.

## 3) Codebase Orientation Map

### Top-Level Layout
- Core directories: `dispatch_optimizer/`, `frontend/`, `tests/`, `sql/`, `tools/`, `examples/`, `data/raw/`
- Key docs: `README.md`, `AGENTS.md`

### Backend Classification
- Authoritative business logic:
  - `dispatch_optimizer/engine_core.py`
  - `dispatch_optimizer/assignment_core.py`
  - `dispatch_optimizer/run_generation_core.py`
  - `dispatch_optimizer/preprocess_core.py`
  - `dispatch_optimizer/routing_core.py`
  - `dispatch_optimizer/providers_core.py`
  - `dispatch_optimizer/models_core.py`
- Compatibility façades (re-export):
  - `dispatch_optimizer/engine.py`, `assignment.py`, `run_generation.py`, `preprocess.py`, `routing.py`, `providers.py`, `models.py`
- CLI entry:
  - `dispatch_optimizer/cli.py`

### Frontend Classification
- Entry and UI shell:
  - `frontend/index.html`
- Main controller + local preview planner:
  - `frontend/app.js` (largest file; mixed concerns)
- UI-only/pure helpers:
  - `frontend/modules/driver-assignment-summary.js`
  - `frontend/modules/zone-utils.js`
- Compatibility shim:
  - `frontend/overrides.js` (shim-only)

### Tests/Tools/Data Classification
- Tests:
  - `tests/test_dispatch_engine.py` (backend behavior)
  - `tests/test_frontend_behavior_parity.py` (frontend parity)
  - `tests/test_project_governance.py` (contract/docs guards)
  - other data/source guard tests
- Tools:
  - `tools/refresh_sample_master_data.py`
  - `tools/recycle.ps1`
- Raw/source:
  - `data/raw/*.csv`
- Example payloads:
  - `examples/sample-dispatch-input.json`

## 4) README / Code Consistency Risks (No Changes Applied)

1. **Priority wording drift risk**
   - README contains both old and newer optimization-priority wording in different sections.
   - Risk: future contributors may enforce wrong objective order in refactors/tests.

2. **run_id terminology ambiguity**
   - Some README wording still references `run_id` semantics while public output contract is `plan_id`.
   - Risk: accidental reintroduction of `run_id` in public output or tests.

3. **Frontend local planner vs backend authority**
   - README correctly states backend authority, but frontend local planner remains substantial.
   - Risk: parity drift if refactors change one side only.

4. **CLI runtime gap**
   - Unit tests pass, but CLI sample command crashes in this environment.
   - Risk: release confidence gap for end-to-end invocation path.

## 5) Proposed Next Steps (Preview Only)

### Proposed Phase 3 (Backend, behavior-preserving)
- Split `assignment_core.py` internals into helper builders:
  - objective stage composition
  - greedy sort-key composition
  - explanation annotation helpers
- Reduce duplication in `engine_core.py` plan/assignment aggregation paths.
- Preserve all public imports and output contracts.

### Proposed Phase 4 (Frontend, behavior-preserving)
- Split `frontend/app.js` by concern:
  - snapshot adapter
  - planner scoring
  - CSV parsing/import
  - render utilities
- Keep same UI structure and same business semantics.

