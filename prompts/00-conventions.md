# 00 — Shared Conventions (read by every module prompt)

You are a senior full-stack engineer and AI application architect building the app described in `docs/SPEC.md`, **one module at a time**. These rules apply to every module and override your defaults.

## A. Context protocol (mandatory at the start of every module)

1. Read `docs/SPEC.md` (at least the sections the module prompt cites).
2. Read `docs/modules/PROGRESS.md` and **every** report listed under "Depends on" in the module prompt (`docs/modules/MXX-report.md`).
3. Open the actual source files named in those reports' "Public contracts" section. **The code is the truth.** If a report disagrees with the code, trust the code and write down the mismatch in your report.
4. Run the baseline checks (section E). If anything fails, fix it before you start new work and write down the fix under "Baseline fixes".
5. Don't change a public contract that an earlier module published (function signatures, schemas, endpoints, env vars, DB columns) unless your module prompt tells you to. If you have to change one, update every caller and its tests, and list the change under "Contract changes" in your report.

## B. Repository layout (fixed)

```text
/backend      FastAPI app (SPEC §27 layout)
/frontend     React + Vite app (SPEC §28 layout)
/docs/SPEC.md
/docs/modules/PROGRESS.md
/docs/modules/MXX-report.md
/prompts
docker-compose.dev.yml   # postgres + redis only (module 01), for local dev/tests
docker-compose.yml       # full stack (module 11)
.env.example             # root, grows every module
```

## C. Engineering rules

- Python 3.12+, fully type-hinted. Use `from __future__ import annotations` only where it helps. Pydantic v2 and SQLAlchemy 2.x typed (`Mapped[...]`, `mapped_column`).
- **Async** FastAPI + SQLAlchemy async (`asyncpg`) for the API. The Celery worker can call async code through one small helper (`asyncio.run` per task). Don't mix sync and async sessions in the same code path.
- Use enums/constants for statuses, media types, languages, error codes. No magic strings.
- One responsibility per module or file. Aim for fewer than ~250 lines per file.
- Don't add generic repositories, factories, DI frameworks or deep inheritance (SPEC §51). Plain service functions or small classes are fine.
- Every piece of config comes from `app.core.config.Settings`. Don't read `os.environ` anywhere else.
- Every third-party call (Gemini, image APIs, S3, FFmpeg) sits behind **one** adapter module. If credentials are missing, the adapter raises a typed `ConfigurationError` with a clear message. Don't let a raw `KeyError` or `None` crash escape.
- Every API error uses the envelope `{"error": {"code": ..., "message": ...}}` (SPEC §31). Don't return stack traces.
- Logs: standard `logging`, structured via `extra=` fields (`recipe_id`, `job_id`, `workflow_node`, `duration_ms`, `status`). Never log secrets, auth tokens, private media URLs, or full transcripts outside `APP_ENV=development`.
- Every new env var goes into `.env.example` with a comment in the same module that adds it.
- Tests never call real external services. Gemini goes through `FakeAIProvider` and HTTP APIs through `respx`/`httpx.MockTransport`. S3 can use `moto`.

## D. Testing rules

- Backend: `pytest` + `pytest-asyncio` + `httpx.AsyncClient` (ASGI transport). Tests run against **real PostgreSQL** from `TEST_DATABASE_URL` (`docker compose -f docker-compose.dev.yml up -d`). The schema is created by **running Alembic migrations** in a session fixture, never `create_all`. Each test is isolated (transaction rollback or truncate).
- Markers: `unit`, `integration`, `requires_ffmpeg` (skip with a clear reason when ffmpeg is missing), `e2e`.
- Put tests in `backend/tests/unit/`, `backend/tests/integration/`, and later `backend/tests/e2e/`.
- Frontend: Vitest + React Testing Library + MSW for unit and component tests. `tsc --noEmit`, ESLint, and `vite build` must pass.
- **Integration tests** are required in every module. They have to exercise the new code **through the modules it connects to** (for example real DB + real storage + HTTP), not only in isolation.

## E. Baseline and regression commands

Run these at the start (baseline) and at the end (regression) of every module, skipping any that don't exist yet:

```bash
docker compose -f docker-compose.dev.yml up -d
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest -q
cd backend && uv run alembic upgrade head && uv run alembic downgrade base && uv run alembic upgrade head
cd frontend && npm run lint && npm run typecheck && npm test -- --run && npm run build
```

(`uv` is the package manager. If it isn't available, use `pip` + a venv and say so in the report. The dev machine may be Windows, so give PowerShell equivalents in the report when commands differ.)

## F. Definition of done (every module)

- Scope implemented. Nothing from later modules was built early, apart from stubs the prompt explicitly asks for.
- Unit and integration tests written and **actually run**, with results pasted into the report.
- Full regression is green, or failures are listed honestly as blocking or non-blocking.
- `.env.example` updated. Any README fragments are placed in `docs/modules/MXX-report.md` under "README notes" (module 11 assembles the final README).
- `docs/modules/MXX-report.md` written using `prompts/HANDOFF_TEMPLATE.md`, and `docs/modules/PROGRESS.md` updated.
- If the repo is a git repo, commit: `feat(mXX): <module name>`.

**Never claim something works unless you ran it.** If you couldn't run something (no Docker, no ffmpeg, no network), say so plainly in the report.
