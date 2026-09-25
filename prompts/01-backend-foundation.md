# Prompt 01 — Backend Foundation

**Depends on:** nothing (first module). **SPEC:** §1, §8, §9, §27, §29, §31, §32, §38, §40, §51.

## Context intake
1. Read `prompts/00-conventions.md` and follow it in full.
2. Read `docs/SPEC.md` §8, §9, §27, §29, §31, §32, §38.
3. This is the first module, so there are no earlier reports. Create `docs/modules/PROGRESS.md` with a table: `Module | Status | Report | Tests (pass/skip/fail) | Key contracts`.

## Goal
A bootable FastAPI backend with configuration, logging, a consistent error envelope, the async DB layer, **every** SQLAlchemy model the app needs, and an initial Alembic migration. This module has no business endpoints except `/api/v1/health`.

## Build

### 1. Project scaffold
- `backend/pyproject.toml`: managed by `uv`. Runtime deps: fastapi, uvicorn[standard], pydantic>=2, pydantic-settings, sqlalchemy[asyncio]>=2, asyncpg, alembic, psycopg[binary] (Alembic sync driver). Dev deps: pytest, pytest-asyncio, httpx, ruff, mypy. Configure ruff (line length 100, sensible rule set: E,F,I,B,UP,SIM,ASYNC), mypy (strict-ish on `app/`), and pytest (markers `unit`, `integration`, `requires_ffmpeg`, `e2e`; `asyncio_mode=auto`).
- The SPEC §27 folder tree is created **only as far as this module needs it**. Don't create empty placeholder files for later modules.
- `docker-compose.dev.yml` at the repo root: `postgres:16` and `redis:7` with healthchecks, named volumes, and a second DB `recipebook_test` (init script).

### 2. `app/core/config.py`
- `Settings(BaseSettings)` covering every SPEC §29 variable, plus: `CORS_ORIGINS` (list), `LOG_LEVEL`, `PUBLIC_BASE_URL` (for canonical URLs later), `TEST_DATABASE_URL`, and `MAX_AUDIO_MB`/`MAX_VIDEO_MB`/`MAX_IMAGE_MB`/`MAX_COOKING_IMAGES` (used by module 02; defaults 50/500/10/20).
- `AppEnv` enum (`development`, `test`, `production`). Use `SecretStr` for every key or secret.
- A cached `get_settings()` function. Don't create a module-level mutable singleton beyond that cache.
- Production validation: when `APP_ENV=production`, reject wildcard CORS and a missing `DATABASE_URL`. Don't require AI keys at boot. They get checked lazily by the adapters (conventions C).

### 3. `app/core/logging.py`
- `configure_logging(settings)`: JSON formatter in production and a readable one in development. Include `extra` fields.
- A `redact()` helper and a logging filter that masks any value from a `SecretStr` setting and any `Authorization` header.
- Request logging middleware: method, path, status, duration_ms, request_id (generate it and return it in `X-Request-ID`). Don't log query strings that could contain tokens.

### 4. `app/core/errors.py`
- `ErrorCode` StrEnum: `VALIDATION_ERROR, NOT_FOUND, CONFLICT, UNSUPPORTED_MEDIA, FILE_TOO_LARGE, EMPTY_UPLOAD, CORRUPTED_MEDIA, CONFIGURATION_ERROR, RATE_LIMITED, UNAUTHORIZED, RECIPE_PROCESSING_FAILED, INTERNAL_ERROR`.
- `AppError(Exception)` (code, message, http_status, and optional `details` that are safe to show), plus subclasses `NotFoundError`, `ConflictError`, `ConfigurationError`, `MediaValidationError`.
- An `ErrorResponse` Pydantic model for OpenAPI.
- Exception handlers registered in `main.py` for `AppError`, `RequestValidationError` (mapped to `VALIDATION_ERROR`, with field-level details), `StarletteHTTPException`, and a catch-all `Exception`. The catch-all logs the traceback server-side and returns `INTERNAL_ERROR` with a generic message.

### 5. `app/db/`
- `base.py`: `DeclarativeBase` with a naming convention for constraints (Alembic-friendly), plus UUID-PK and timestamp mixins (`created_at`, `updated_at` with server defaults and on-update).
- `session.py`: async engine and `async_sessionmaker` created from settings, the `get_session` FastAPI dependency, and a `session_scope()` async context manager for non-HTTP code (the worker uses it in module 05).

### 6. `app/models/` — every table, created now so later modules only add small migrations
Enums in `app/models/enums.py`: `RecipeStatus` (SPEC §9, exact values), `JobStatus` (`QUEUED, RUNNING, COMPLETED, FAILED`), `JobStep` (the SPEC §9 processing states, so the UI can show progress), `MediaType` (SPEC §8), `Language` (`auto, en, bn, hi`), `BlogStatus` (`DRAFT, PUBLISHED`), `StepImageStatus` (`MATCHED, UNMATCHED, MANUAL`).

Tables (SPEC §8 minimum **plus** the columns marked +, which later modules need):
- `recipes`: SPEC fields. `language` is the requested language and + `detected_language`. + `cuisine`, `category`, `keywords` (ARRAY(String)), `hero_media_id` (FK media_assets, nullable, `use_alter`), `published_at`, `owner_id` (nullable String, for the auth architecture). `slug` is unique and nullable until the blog exists. Add an index on `status`.
- `ingredients`: SPEC fields, `order` → name the column `position`. + `normalized_name` (lowercase, used for similarity and image lookup). **Unique (recipe_id, position)**.
- `recipe_steps`: SPEC fields. **Unique (recipe_id, step_number)**.
- `cooking_suggestions`: `position` + **unique (recipe_id, position)**.
- `media_assets`: SPEC fields. `url` → store `storage_key` (not a URL, SPEC §7) + `original_filename` (sanitized), `size_bytes`, `metadata` → name the attribute `meta` (JSONB), + `position` (order of cooking photos).
- `step_images`: SPEC fields. `step_id` is nullable (unmatched) + `status` (StepImageStatus), `reason`. **Unique (media_asset_id)**, so one photo maps to at most one step.
- `ingredient_images`: SPEC fields + `provider`, `alt_text`. **Unique (ingredient_id)**.
- `blogs`: SPEC fields + `status` (BlogStatus), `primary_keyword`, `secondary_keywords` (ARRAY), `og_title`, `og_description`, `hero_alt_text`, `json_ld` (JSONB), `faq` (JSONB), `published_at`. **Unique (recipe_id)** and **unique slug**.
- `jobs`: SPEC fields. `current_step` is a JobStep, `progress` is an int from 0 to 100, `error` is a safe message + `error_code`, `attempts` (int), `celery_task_id`.
- Relationships use `cascade="all, delete-orphan"` from recipe to children, with `ondelete="CASCADE"` FKs. Keep each model file short: `recipe.py` (recipe, ingredient, step, suggestion), `media.py` (media_asset, step_image, ingredient_image), `blog.py`, `job.py`.

### 7. Alembic
- `alembic.ini` + `migrations/env.py` read the URL from `Settings` (converting the async URL to the sync driver). `target_metadata = Base.metadata`. Imports go through `app.models` so autogenerate sees every table.
- Write **one hand-reviewed initial migration** that creates all tables, enums, constraints, and indexes. `downgrade()` must drop everything cleanly, including the PG enum types.

### 8. `app/main.py`
- An app factory `create_app(settings) -> FastAPI` that sets up the title, version, `/api/v1` router prefix, CORS from settings, the logging middleware, and error handlers. `GET /api/v1/health` returns `{status, version, database: "ok"|"error"}` (runs `SELECT 1`) and has a full OpenAPI summary, description, and response model.

## Tests
**Unit (`tests/unit/`)**
- Settings: defaults load; production rejects `CORS_ORIGINS=["*"]`; secrets aren't exposed in `repr`.
- Logging redaction filter masks secret values and `Authorization` headers.
- Error envelope: a route that raises `NotFoundError` returns 404 with the exact envelope. An unhandled exception returns 500 `INTERNAL_ERROR` with no traceback in the body. A validation error returns 422 `VALIDATION_ERROR`.
- Enum values match SPEC §9 exactly.

**Integration (`tests/integration/`) — DB + migrations + app**
- Session fixture: runs `alembic upgrade head` against `TEST_DATABASE_URL` and gives each test a rolled-back transaction.
- Migration round trip: `upgrade head → downgrade base → upgrade head` succeeds, and `alembic check` (or autogenerate diff) reports **no drift** between models and migration.
- Insert a recipe with ingredients, steps, suggestions, media, and blog. Deleting the recipe cascades.
- Uniqueness: a duplicate `(recipe_id, position)` ingredient raises IntegrityError, and so do a duplicate blog slug and a duplicate `ingredient_images.ingredient_id`.
- `GET /api/v1/health` reports `database: ok` against the real DB.
- `/openapi.json` is served and `/api/v1/health` has a summary.

## Acceptance
Run the full conventions §E backend commands. Everything must be green: ruff, format, mypy, pytest, and the alembic round trip.

## Handoff
Write `docs/modules/M01-report.md` using `prompts/HANDOFF_TEMPLATE.md`. Section 4 must list, at minimum: the `Settings` fields, `get_settings`, `create_app`, `get_session`, `session_scope`, every enum with its values, every table with its unique constraints, the migration revision id, `AppError` and its subclasses, `ErrorCode`, and the test fixtures later modules should reuse (their names and file). Update `PROGRESS.md`.
