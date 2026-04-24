# Summary
- What changed?

# Files Changed
- List main files changed.

# Business Behavior Impact
- Does this change dispatch assignment behavior?
- Does it change scoring weights?
- Does it change priority order?
- Does it change hard/soft constraints?
- Does it change zone behavior?
- Does it change plan aggregation?

# Output Contract Impact
- Does this change plans / order_assignments / exceptions?
- Does this change plan_id?
- Does this expose run_id publicly?

# Frontend/UI Impact
- Does this change the primary Driver -> Vehicle -> Orders view?
- Does this expose run_id, ETA, stop sequence, or departure in the primary view?

# Tests Run
- node --check frontend/app.js
- node --check frontend/overrides.js
- python -m unittest discover -s tests -v

# Risk / Rollback Notes
- Risks:
- Rollback plan:

# Decision Needed
- Any business decision required?
- Any behavior change requiring approval?
