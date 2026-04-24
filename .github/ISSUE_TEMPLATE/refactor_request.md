---
name: Refactor Request
about: Request structural improvements without behavior changes.
title: "[REFACTOR] "
labels: refactor
assignees: ""
---

## Scope
- Files/modules in scope:

## Motivation
- Why this refactor is needed:

## Behavior Preservation
- Confirm no business behavior change is intended.
- Confirm no output contract change is intended.

## Validation Plan
- node --check frontend/app.js
- node --check frontend/overrides.js
- python -m unittest discover -s tests -v

## Risk / Rollback
- Risks:
- Rollback plan:
