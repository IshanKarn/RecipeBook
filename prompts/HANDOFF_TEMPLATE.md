# MXX — <Module name> — Handoff Report

> Written by module XX at completion. Read by every later module that depends on it.
> Keep it factual. Paste real command output (trimmed); do not paraphrase test results.

## 1. Status
- Result: DONE | DONE WITH ISSUES | BLOCKED
- Date:
- Depends on: M.., M..

## 2. Scope delivered
- Bullet list of what was built (map each to SPEC §).
- Explicitly deferred items (and to which module).

## 3. Files
| Path | Purpose |
|------|---------|

## 4. Public contracts (what later modules may rely on)
Exact signatures / shapes, e.g.
```python
async def get_recipe(session: AsyncSession, recipe_id: UUID) -> Recipe
class StorageService(Protocol): ...
```
- Endpoints added (method, path, request, response, status codes)
- DB tables/columns/constraints added (+ migration revision id)
- Enums/constants added
- Env vars added (name, default, required?)

## 5. Contract changes to earlier modules
- None | list each change, why, and which callers/tests were updated.

## 6. Design decisions & deviations from SPEC
- Decision — reason.

## 7. Test results
### Baseline (before changes)
```
<command + trimmed output>
```
### Module unit tests
```
<command + output: N passed, M skipped (reason)>
```
### Integration tests (with: M.., M..)
```
<command + output>
```
### Full regression + lint + types
```
ruff: ...
mypy: ...
pytest: ...
alembic up/down/up: ...
frontend lint/typecheck/test/build: ...
```

## 8. Known issues
| Severity (blocking/non-blocking) | Issue | Suggested fix / owner module |
|---|---|---|

## 9. Notes for the next module
- Things the next prompt must know (gotchas, fixtures to reuse, helper functions, how to run things on Windows).

## 10. README notes
- Setup/usage fragments to be assembled into the final README by module 11.
