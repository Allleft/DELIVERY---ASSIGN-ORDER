# GitHub Workflow Guide

## 1. Branch Strategy
- `main` is the stable branch.
- Feature/refactor work should happen on short-lived branches.
- Use Pull Requests for risky or behavior-touching changes.
- Direct commits to `main` should be limited to approved, small, low-risk changes.

## 2. Commit Workflow
After any approved code or documentation change:
1. Run tests first.
2. Minimum validation:
   - `node --check frontend/app.js`
   - `node --check frontend/overrides.js`
   - `python -m unittest discover -s tests -v`
3. If tests pass, commit and push.
4. Report commit hash, branch, and `git status`.

## 3. No-Commit Rules
Do **not** commit/push if:
- tests fail
- business behavior may change without approval
- output contract may change
- secrets or local files are staged
- `tmp/` or `tmp/backups/` are staged

## 4. PR Checklist
- business behavior unchanged or explicitly approved
- output contract unchanged or explicitly approved
- tests passed
- `README.md` updated if structure or governance changed
- rollback plan included

## 5. Branch Protection (Manual GitHub Settings)
Recommended GitHub repository settings:
- protect `main`
- require pull request before merge
- require CI checks to pass
- block force push
- block branch deletion
- optionally require linear history

## 6. Release / Tag Strategy (Recommendation)
- `v0.1.0` initial stable baseline
- `v0.2.0` zone-first policy baseline
- `v0.3.0` structure optimization baseline

Do not create releases/tags without explicit approval.
