# Phase 4E-A Metrics Baseline (Sample 20/7/9)

This note records the sample run performance diagnosis before and after the Phase 4E-A
metrics-only instrumentation pass.

## Sample Scenario

- Orders: 20
- Drivers: 7
- Vehicles: 9
- Geocoder mapping: Depot only (for driver coordinates)

## Before (pre-4E-A instrumentation probe)

- route_plan_calls: 63
- route_cache_hits: n/a (not exposed in logs)
- route_cache_misses: n/a (not exposed in logs)
- route_plan_total_ms: 126163.70
- route_plan_timeout_count: n/a (not exposed in logs)
- candidate_count: 238
- validated_candidate_count: 63
- stage=plan_dispatch elapsed_ms: baseline probe showed plan_dispatch dominated total
- stage=total elapsed_ms: 127239.28

## After (4E-A metrics-only, service log fields)

- route_plan_calls: 63
- route_cache_hits: 0
- route_cache_misses: 63
- route_plan_total_ms: 127230.24
- route_plan_timeout_count: 0
- candidate_count: 238
- validated_candidate_count: 63
- stage=plan_dispatch elapsed_ms: 129180.02
- stage=total elapsed_ms: 129183.56

## Notes for Phase 4E-B

- Candidate-stage route validation remains the dominant cost.
- CP-SAT is still not the bottleneck.
- 4E-B can evaluate candidate-stage OR-Tools time-limit reduction, with contract/behavior
  regression checks retained.

## Phase 4E-B Runtime A/B Findings (20 orders / 7 drivers / 9 vehicles)

Median total elapsed (runtime-only monkeypatch experiment):

- `time_limit=2.0s`: `~127.1s`
- `time_limit=1.0s`: `~64.1s`
- `time_limit=0.5s`: `~32.5s`
- `time_limit=0.25s`: `~16.8s`

Observed behavior across the experiment set:

- `contract_exact=true` in all runs (top-level keys remained `plans / order_assignments / exceptions`).
- `assigned=20`, `unassigned=0`, `exceptions=0` in all runs.
- No added/removed assigned order IDs.
- No `vehicle_id` or `status` drift.
- One baseline run (`2.0#3`) showed `driver_id` drift, indicating existing solver non-determinism rather than degradation caused by lower candidate-stage route `time_limit`.

## Phase 4E-C Default Decision

- Chosen default for candidate-stage route validation `time_limit`: **`0.25s`**.
- Keep diagnostic override path available:
  - code-level: `DispatchEngineConfig(candidate_route_time_limit_seconds=2.0)`
  - runtime env (Office backend): `OFFICE_DISPATCH_CANDIDATE_ROUTE_TIME_LIMIT_SECONDS`
