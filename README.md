# Delivery Dispatch Optimizer

Order assignment system for delivery dispatch scenarios. The current core model is **trip grouping + assignment**: orders are grouped into trips (internal compatibility objects may still use `run` terms), then drivers and vehicles are assigned.

Top-level output contract is fixed: `plans / order_assignments / exceptions`.

## 1. Project Overview

- Problem solved: Given orders, drivers, and vehicles, generate feasible assignments showing which driver carries which orders with which vehicle.
- Core capabilities: normalization, trip grouping, global driver/vehicle assignment, exception reporting, and business-facing frontend workspace.
- Top-level input/output:
  - Input: `config + orders + drivers + vehicles`
  - Output: `plans / order_assignments / exceptions`
- Default frontend primary view: `Driver Assignment Summary` (`Driver -> Vehicle -> Orders`)
- Travel time strategy: `cache first -> Google Routes -> Haversine fallback`
- Master data source of truth:
  - `data/raw/driver-raw-data.csv`
  - `data/raw/vehicle-raw-data.csv`
  - `data/raw/zone-postcode-raw-data.csv`

### Authoritative Result Source

- Backend `dispatch_optimizer.DispatchEngine` is the authoritative source of truth for dispatch results.
- Frontend is for input editing and result visualization; it includes local preview logic, but production truth comes from backend output.

## 2. Project Main Flow

1. Read snapshot input (compatible with both flat config top-level keys and nested `config`).
2. Preprocess orders/drivers/vehicles:
   - map postcode to zone,
   - normalize coordinates and defaults,
   - `service_minutes` has been removed from the input model; system uses fixed dwell time (`FIXED_STOP_MINUTES = 10`).
3. Trip grouping:
   - grouped by `dispatch_date + zone_code + bucket` as the primary grouping key.
4. Candidate enumeration and assignment:
   - enumerate feasible `(trip, driver, vehicle)` candidates,
   - use coarse time feasibility estimation (not dependent on detailed stop routing).
5. Global solving:
   - satisfy hard constraints first,
   - optimize soft objectives (urgency, preferred zone, continuity, capacity waste, etc.).
6. Output:
   - `plans`: trip-level plan summaries aggregated by `dispatch_date + driver_id + vehicle_id`
   - `order_assignments`: order-level assignment results
   - `exceptions`: reasons for unassigned or invalid items
7. Frontend output:
   - primary view: `Driver Assignment Summary` (`Driver -> Vehicle -> Orders`)
   - secondary view: `Assignment Groups (Secondary)` for troubleshooting and reconciliation

> detailed routing is no longer the primary output. `routing_core.py` remains for compatibility and optional feasibility checks.

## 3. Directory Structure

```text
.
|- dispatch_optimizer/
|- frontend/
|- sql/
|- tests/
|- tools/
|- examples/
|- data/
|  |- raw/
|  `- excel/
|- docs/
|- README.md
`- AGENTS.md
```

- `dispatch_optimizer/`: backend dispatch core (preprocess, grouping, assignment, providers, CLI).
- `frontend/`: business workspace frontend (input editing + result rendering).
- `sql/`: dispatch-layer schema and master-data import/export scripts.
- `tests/`: backend tests, frontend parity tests, and governance guards.
- `tools/`: helper scripts (sample refresh, recycle-bin delete, etc.).
- `examples/`: runnable sample snapshot input.
- `data/raw/`: raw source-of-truth CSV files.
- `data/excel/`: Excel exports derived from raw files.

## 4. Key Files / Modules

### Frontend

- `frontend/index.html`
  - Input: none (static page layout)
  - Output: DOM containers and script load order
  - Role: business workspace structure, action buttons, output sections, empty-state copy
  - Called by: browser entry page

- `frontend/app.js`
  - Input: table state + developer-mode JSON
  - Output: local preview result + UI rendering
  - Role: page orchestrator (state, table mapping, validation, render flow)
  - Depends on: `DeliveryZoneUtils`, `DeliveryDriverAssignmentSummary`, render utils

- `frontend/modules/driver-assignment-summary.js`
  - Input: `order_assignments` + `plans`
  - Output: `driver -> vehicle -> orders` summary structure
  - Role: primary business summary aggregation without exposing run-level technical details

- `frontend/modules/render-utils.js`
  - Input: view state and result fields
  - Output: display name mapping and business-friendly explanation conversion
  - Role: pure rendering helper with fallback behavior

- `frontend/overrides.js`
  - Input: global `window`
  - Output: shim marker only
  - Role: compatibility shim; does not hold core business logic

### Backend (façade + core)

- `dispatch_optimizer/engine.py` + `dispatch_optimizer/engine_core.py`
  - Input: normalized entities + providers
  - Output: `DispatchEngineResult(plans/order_assignments/exceptions)`
  - Role: main orchestration pipeline

- `dispatch_optimizer/models.py` + `dispatch_optimizer/models_core.py`
  - Role: shared data contracts for order/driver/vehicle/trip/assignment/exception

- `dispatch_optimizer/preprocess.py` + `dispatch_optimizer/preprocess_core.py`
  - Input: raw snapshot entities
  - Output: normalized snapshot + preprocessing exceptions

- `dispatch_optimizer/run_generation.py` + `dispatch_optimizer/run_generation_core.py`
  - Input: normalized orders
  - Output: internal grouping objects for assignment

- `dispatch_optimizer/assignment.py` + `dispatch_optimizer/assignment_core.py`
  - Input: grouped trips, drivers, vehicles
  - Output: candidate list + selected assignment set
  - Notes: coarse timing estimator first; detailed routing is optional, not required as primary chain

- `dispatch_optimizer/routing.py` + `dispatch_optimizer/routing_core.py`
  - Role: compatibility routing module, not the primary output driver

- `dispatch_optimizer/providers.py` + `dispatch_optimizer/providers_core.py`
  - Role: geocoding/travel-time providers, caching, and Google Routes fallback

- `dispatch_optimizer/cli.py`
  - Input: snapshot JSON file
  - Output: serialized result JSON (`plans / order_assignments / exceptions`)
  - Role: CLI entry and provider assembly

### Tools and SQL

- `tools/refresh_sample_master_data.py`
  - refreshes sample master sections from raw driver/vehicle CSV
  - **Rule: `tools/refresh_sample_master_data.py` only updates `drivers` and `vehicles`**

- `tools/recycle.ps1`
  - recycle-bin delete script (no direct physical delete)

- `sql/dispatch-*.sql`, `sql/vehicle-*.sql`
  - dispatch-layer snapshot/output tables and vehicle import/export flow

## 5. Data Sources and Master Data Flow

### Source of Truth vs Generated Artifacts

- **Raw Source of Truth**:
  - `data/raw/zone-postcode-raw-data.csv`
  - `data/raw/driver-raw-data.csv`
  - `data/raw/vehicle-raw-data.csv`
- **Generated Artifact**:
  - auto-refreshed sections (`drivers/vehicles`) inside `examples/sample-dispatch-input.json`
- **Frontend Default Sample State**:
  - front page starts with empty `orders`, while drivers/vehicles are immediately visible

### Region Model

- Order input field: `postcode`
- System-mapped region key: `zone_code`
- Grouping and preference matching use `zone_code`
- Exception code for unknown mapping: `POSTCODE_NOT_MAPPED`

## 6. Frontend Notes

- Default input mode: table editing for orders/drivers/vehicles, plus CSV order import.
- Primary result view: `Driver Assignment Summary` (`Driver -> Vehicle -> Orders`).
- Secondary result view: `Assignment Groups (Secondary)` for grouped detail inspection.
- Developer mode: full JSON inspection and round-trip apply.
- Input shape remains `config / orders / drivers / vehicles`.

## 7. Dispatch Algorithm Notes

- Internal grouping objects are retained; business semantics are trip grouping + assignment.
- Hard constraints include:
  - designated driver,
  - driver availability,
  - vehicle availability,
  - capacity fit,
  - resource/time overlap constraints.
- Zone-First assignment policy (2026-04-24) and objective stage order:
  - `hard constraints -> urgent coverage -> preferred-zone match -> minimize driver-day zone spread -> same-day vehicle minimization -> assignment coverage -> used drivers / balance / normal objective`
- Key weights currently include:
  - `preferred_zone_bonus=3000`
  - `zone_mismatch_penalty=2500`
  - `vehicle_switch_penalty`
- Output semantics:
  - `plans`: grouped plan summaries
  - `order_assignments`: order-level assignments
  - `exceptions`: failure reasons and suggested actions
  - Includes driver utilization exception codes such as `DRIVER_UNUSED_NO_FEASIBLE_CANDIDATE`

## 8. Configuration and Run Commands

### Common commands

```bash
node --check frontend/app.js
node --check frontend/overrides.js
python -m unittest discover -s tests -v
```

### CLI example

```bash
python -m dispatch_optimizer.cli examples/sample-dispatch-input.json
```

### Google Routes and fallback

- Primary external travel-time source: **Google Routes API**
- Flow: `cache first -> Google Routes -> Haversine fallback`
- Typical config keys:
  - `google_routes_api_key`
  - `google_routes_base_url`
  - `routing_preference`
  - `departure_time_strategy`
  - `request_timeout_seconds`
  - `max_retries`
  - `backoff_seconds`

## 9. Important Rules and Constraints

- Top-level output contract is fixed: `plans / order_assignments / exceptions`.
- Public linkage uses `plan_id`.
- **Plan ID Migration (2026-04-23)**:
  - `order_assignments[*]` is linked by the same `plan_id`.
- Region model is fixed: `postcode + zone_code`.
- Driver preference field: `preferred_zone_codes`.
- Legacy compatibility:
  - old fields can be read for compatibility,
  - new outputs must not write `zone_id` or `preferred_zone_ids`.
- `service_minutes` has been removed from input; fixed stop dwell time is 10 minutes internally.
- Do not physically delete files; use `tools/recycle.ps1`.

## 10. Known Boundaries / Notes

### Compatibility layers

- Most `dispatch_optimizer/*.py` are façade files; implementation is in `*_core.py`.
- `routing_core.py` is retained but is not the primary output chain.
- Frontend still keeps compatibility branches; effective behavior comes from the final active logic path.

### Technical debt

- `frontend/app.js` is still large and historically accumulated, so maintenance cost is high.
- Frontend local planner and backend authoritative logic coexist; parity checks are important.
- Governance tests guard critical README statements; update tests together when wording changes.
