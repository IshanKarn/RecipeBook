# Prompt 11 — Docker, Production Hardening, E2E, README, Final Verification

**Depends on:** all of M01–M10. **SPEC:** §29, §30, §32, §37, §38, §39, §48, §49, §52.

## Context intake
1. Follow `prompts/00-conventions.md` §A.
2. Read `docs/modules/PROGRESS.md` and **every** report M01–M10: every "Known issues" table, every "README notes" section, and the M10 reverse-proxy routing requirements.
3. Run the full baseline (backend + frontend + migrations). Every open **blocking** issue from earlier reports gets fixed first, and each one is recorded under "Baseline fixes".

## Goal
The app starts with `docker compose up --build`, is hardened for production, passes an end-to-end smoke test inside Docker, and ships with a README that matches the implementation exactly.

## Build

### 1. Backend image — `backend/Dockerfile` (multi-stage)
- The builder stage uses `uv` to build a venv from the lockfile. The runtime stage is `python:3.12-slim` with `ffmpeg` installed from apt, a **non-root** user (uid 10001), no build tools, `PYTHONDONTWRITEBYTECODE`/`PYTHONUNBUFFERED`, and a `HEALTHCHECK` against `/api/v1/health`.
- Entrypoints (a small `docker/entrypoint.sh` or separate commands):
  - `api`: gunicorn with uvicorn workers, with the worker count coming from an env var
  - `worker`: `celery -A app.workers.celery_app worker`
  - `migrate`: `alembic upgrade head`
- Migrations run as a **separate one-shot service**, never automatically inside every API replica.
- `.dockerignore`.

### 2. Frontend image — `frontend/Dockerfile`
- A Node build stage (`npm ci && npm run build`, with `VITE_API_BASE_URL` as a build arg defaulting to `/api/v1`), then an `nginx:alpine` **unprivileged** image (`nginxinc/nginx-unprivileged`) that serves `dist/`.
- `frontend/nginx.conf`:
  - SPA fallback
  - `/api/` proxied to the backend (with `client_max_body_size` matching the upload limits and longer timeouts for uploads)
  - `/blog/`, `/sitemap.xml`, and `/robots.txt` proxied to the backend SSR (M10)
  - gzip, and long cache for hashed assets with no-cache for `index.html`
  - security headers: CSP (`default-src 'self'`; `img-src 'self' https://upload.wikimedia.org https://images.unsplash.com https://images.pexels.com data:`; `media-src 'self' <S3 origin if configured>`; `script-src 'self'` plus the JSON-LD, which isn't executable so it needs no hash, but verify), `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, and `frame-ancestors 'none'`

### 3. `docker-compose.yml` (SPEC §37)
- Services: `postgres` (healthcheck, volume), `redis` (healthcheck), `migrate` (runs once, `depends_on: postgres healthy`), `backend` (depends on migrate `service_completed_successfully`), `worker`, and `frontend` (port 8080 or 5173, whichever you pick; document it). Optional profile `s3` adds `minio` + a bucket-init job to exercise `STORAGE_BACKEND=s3`.
- A shared `media` volume for local storage, mounted by the backend **and** the worker, since both need the files.
- Uses `.env` (copied from `.env.example`). The default `AI_PROVIDER` is `fake` **only** when `GEMINI_API_KEY` is empty. Implement this as an explicit, logged startup decision ("AI_PROVIDER=auto → fake: no GEMINI_API_KEY"), or by requiring the user to set it; document which. Don't fall back to fake silently in production: in `APP_ENV=production`, a missing key with `AI_PROVIDER=gemini` gives a `ConfigurationError` at worker start.
- Keep `docker-compose.dev.yml` (from M01) for local development.

### 4. Production hardening checklist (implement and verify each item; the report gets a table of item → how it was verified)
- Security headers on the API responses (through middleware), in addition to nginx.
- CORS: an explicit origin list in production (checked by the M01 validator).
- Rate limits are active in compose (Redis-backed). Check that the upload and process limits work.
- Secrets appear only in env, `.env` is gitignored, the frontend bundle has **no secrets** (grep `dist/` for `GEMINI`, `SECRET`, and `KEY` values), and the logs contain no secrets, auth headers, private media URLs, or transcripts in production mode (a test captures the logs from a production-mode workflow run and asserts none of those appear).
- Media: presigned-URL expiry is configured, and the local media route enforces access (M03/M07).
- Uploads: body limits are consistent across nginx, the ASGI app, and the validation layer (**one** documented table).
- DB: the pool size comes from settings, `pool_pre_ping`, and statement timeouts.
- Worker: time limits, `acks_late`, `max_retries`, and a periodic cleanup of stuck RUNNING jobs older than N minutes (Celery beat is optional; a simple management command is fine, as long as it's documented).
- Health: `/api/v1/health` checks the DB and Redis. The worker gets its own healthcheck (for example `celery inspect ping`, in compose).
- Graceful configuration errors for every third-party service without credentials: Gemini, Unsplash, Pexels, and S3. Each gives a useful message, and the app still boots.

### 5. End-to-end smoke — `backend/tests/e2e/` (marker `e2e`) + `scripts/e2e-smoke.(sh|ps1)`
Against the **running compose stack**, with `AI_PROVIDER=fake` and Wikimedia mocked, **or** a real Wikimedia hit behind `E2E_ALLOW_NETWORK=1`:
1. `GET /api/v1/health` returns ok (DB + Redis).
2. `POST /api/v1/recipes` with a generated audio file + video + 2 photos through nginx (port 8080) returns 202.
3. Poll the job to COMPLETED (timeout 120 s). The real Celery worker container did the processing.
4. `GET` the recipe and blog: the ingredients, steps, and a sanitized blog are there.
5. PATCH, then publish, then `GET /blog/{slug}` through nginx (SSR) returns 200 with JSON-LD. `GET /api/v1/blog/{slug}` returns 200. Anonymous media URLs from the page return 200/206.
6. `GET /sitemap.xml` lists the slug.
7. A retry and idempotency check with `force=true` shows no duplicate rows (query through the API counts).

The Windows **and** POSIX scripts start compose, wait for health, run pytest `-m e2e`, and tear down with `-v` when `--clean` is passed.

### 6. README.md (root), following SPEC §49 exactly
Put these sections in order: Architecture (the SPEC Mermaid diagram, **updated** to the real components including nginx and the migrate job), the workflow graph (a Mermaid diagram of the real node list), prerequisites, environment variables (a table generated from, or checked against, `Settings`: name, default, required, description), local development (with PowerShell and bash commands), Docker development, database setup, migrations, running the backend, worker (with the Windows `--pool=solo` note), and frontend, running tests (unit, integration, e2e, live_ai), linting, API endpoints (a table + a link to `/docs`), the AI workflow, media storage (local vs S3 + MinIO profile), image attribution and licensing, security model and auth architecture (honest: the `api_key` mode is for admin and server use, and browser auth needs an IdP), production deployment (build, migrate job, env, scaling the API and workers, S3, a CDN for media, backups), and troubleshooting.
- Assemble it from the "README notes" in every report, and **verify every command in the README by running it** (mark any you couldn't run in the report).
- `docs/API.md`: generated from `app.openapi()` by a script (`scripts/export_openapi.py` → `docs/openapi.json` + a Markdown endpoint table). A test fails if `docs/openapi.json` is out of date.

### 7. CI (small)
`.github/workflows/ci.yml`: backend lint, type checks, and tests (with Postgres and Redis service containers, and ffmpeg installed), a migration round trip, frontend lint, typecheck, test, and build, and `docker compose build`. Don't deploy anything.

## Final verification (SPEC §52; paste the actual output of each into the report)
1. Backend tests: every marker except `live_ai`, plus e2e against compose.
2. Frontend typecheck, tests, and build.
3. Ruff, format, mypy, and ESLint.
4. Import check: `python -c "import app.main, app.workers.tasks, app.ai.workflows.graph"` inside the container.
5. `docker compose config` is valid, and `docker compose up --build` gets every service healthy.
6. Migrations: `upgrade head → downgrade base → upgrade head` inside the container, plus `alembic check` shows no drift.
7. OpenAPI: every operation has a summary, description, response model, and error responses (the M03 test, extended to all routes).
8. Fix any obvious errors you find.
9. README cross-check: every env var in `Settings` is documented in the README and `.env.example` (and the reverse). Automate this with a test.

## Handoff
Write `docs/modules/M11-report.md`. It includes the hardening table, the final verification outputs, the list of README commands verified, the remaining known issues with severity, and a "Next steps" list (for example: WebSockets for job status, a real IdP, an embedding similarity strategy, slug redirects, and old-media cleanup). Update `PROGRESS.md` to show every module and the final test totals. **Don't claim anything works that wasn't run.**
