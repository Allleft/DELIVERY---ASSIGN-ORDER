# Repository Guardrails

## Contract and Scope
- Keep the top-level output contract unchanged: `plans / order_assignments / exceptions`.
- Keep the `postcode + zone_code` region model unchanged.
- Do not change DispatchEngine main flow unless explicitly approved.

## Process Rules
- Audit first, then modify.
- Every behavior or contract change must sync `README.md` in the same pass.
- Prefer small, reviewable diffs.

## File Safety
- Do not physically delete files directly.
- If cleanup is required, move files to recycle bin via `tools/recycle.ps1`.

## Git / GitHub Workflow

After every approved code or documentation change:
1. Run relevant tests first.
2. Minimum validation:
   - `node --check frontend/app.js`
   - `node --check frontend/overrides.js`
   - `python -m unittest discover -s tests -v`
3. If tests pass, commit changed files with a clear commit message.
4. Push to origin.
5. Report:
   - commit hash
   - branch
   - git status
6. If tests fail, do not commit or push.
7. If any change may affect dispatch business behavior, stop and ask for approval before committing.
8. Never commit:
   - secrets
   - API keys
   - .env files
   - credentials
   - private keys
   - tmp/backups/
   - cache files
   - local environment files
   - node_modules/
   - __pycache__/

Business behavior changes requiring approval:
- scoring weights
- objective priority order
- hard vs soft constraints
- zone behavior
- plan aggregation
- public output contract
- frontend primary business display
