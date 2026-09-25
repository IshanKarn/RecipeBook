# M01 — Backend Foundation — Handoff Report

## 1. Status
- Result: **DONE**
- Date: 2026-09-25
- Depends on: — (first module)

## 2. Scope delivered
- Backend project scaffold managed by `uv`, with ruff, mypy (strict) and pytest configured (SPEC §1, §27).
- `docker-compose.dev.yml` runs PostgreSQL 16 and Redis 7 with healthchecks, plus a `recipebook_test` database created by an init script.
- `Settings` covers every SPEC §29 variable plus the extras the module prompt asked for, and validates production config (SPEC §29).
- Logging: JSON output in production and readable text in development, secret and Authorization redaction, and per-request access logs with `X-Request-ID` (SPEC §32, §30).
- Consistent error envelope and exception handlers (SPEC §31).
- Async SQLAlchemy engine, `get_session` dependency and `session_scope()` helper.
- Every model the app needs (SPEC §8 plus the extra columns later modules rely on) and every enum (SPEC §9).
- One hand-reviewed initial Alembic migration `0001` (SPEC §38).
- `create_app()` factory and `GET /api/v1/health` (SPEC §39).
- **Deferred:** storage and validation → M02. Business endpoints, auth and rate limits → M03. Anything AI-related → M04+. The full `docker-compose.yml` → M11.

## 3. Files
| Path | Purpose |
|------|---------|
| `docker-compose.dev.yml` | Dev Postgres (**host port 5434**) + Redis (6379) |
| `docker/postgres/init/01-create-test-db.sql` | Creates the `recipebook_test` DB when the volume is first initialised |
| `.env.example` | Root env template (the backend reads `.env` or `../.env`) |
| `.gitignore` | Ignores secrets, venvs, caches, node_modules, local media |
| `backend/pyproject.toml`, `backend/uv.lock` | Dependencies and tool config (ruff, mypy, pytest markers) |
| `backend/app/__init__.py` | `__version__ = "0.1.0"` |
| `backend/app/main.py` | `create_app()`, CORS, middleware, handlers, router; `app` for uvicorn |
| `backend/app/core/config.py` | `Settings`, `AppEnv`, `get_settings`, URL driver helpers |
| `backend/app/core/logging.py` | `configure_logging`, `redact`, filters, formatters, `RequestLoggingMiddleware`, `request_id_var` |
| `backend/app/core/errors.py` | `ErrorCode`, `AppError` + subclasses, `ErrorResponse`, `register_exception_handlers` |
| `backend/app/db/base.py` | `Base` (naming convention, `AsyncAttrs`), mixins, `pg_enum()` |
| `backend/app/db/session.py` | Engine and session factories, `get_session`, `session_scope` |
| `backend/app/models/enums.py` | All domain enums |
| `backend/app/models/recipe.py` | `Recipe`, `Ingredient`, `RecipeStep`, `CookingSuggestion` |
| `backend/app/models/media.py` | `MediaAsset`, `StepImage`, `IngredientImage` |
| `backend/app/models/blog.py` | `Blog` |
| `backend/app/models/job.py` | `Job` |
| `backend/app/models/__init__.py` | Imports every model (Alembic uses it) and re-exports the models and enums |
| `backend/app/api/v1/router.py` | `api_router` (later modules include their routers here) |
| `backend/app/api/v1/health.py` | `GET /api/v1/health` |
| `backend/alembic.ini`, `backend/migrations/env.py`, `script.py.mako` | Alembic config; the URL comes from Settings |
| `backend/migrations/versions/20260925_0001_initial_schema.py` | Initial migration, revision **`0001`** |
| `backend/tests/conftest.py` | Shared fixtures (see §9) |
| `backend/tests/unit/test_{config,logging,errors,enums}.py` | Unit tests |
| `backend/tests/integration/test_{migrations,models,health}.py` | Integration tests |

## 4. Public contracts

### Configuration — `app/core/config.py`
```python
class AppEnv(StrEnum): DEVELOPMENT="development"; TEST="test"; PRODUCTION="production"
class Settings(BaseSettings): ...          # fields below; env names are the UPPERCASE field names
    is_production: bool                    # property
    def secret_values(self) -> list[str]   # all SecretStr values + DB/Redis URL passwords
def get_settings() -> Settings             # lru_cache'd
def to_async_database_url(url: str) -> str # -> postgresql+asyncpg://
def to_sync_database_url(url: str) -> str  # -> postgresql+psycopg:// (Alembic)
```
| Field (env var) | Type | Default |
|---|---|---|
| `app_env` | AppEnv | development |
| `app_name` | str | "RecipeBook API" |
| `log_level` | str | INFO |
| `public_base_url` | str | http://localhost:8000 |
| `cors_origins` | list[str] (CSV or JSON) | ["http://localhost:5173"] |
| `database_url` | str | postgresql+asyncpg://recipebook:recipebook@localhost:5434/recipebook |
| `test_database_url` | str | …/recipebook_test |
| `db_pool_size` / `db_max_overflow` | int | 5 / 10 |
| `db_connect_timeout_seconds` | float | 5.0 |
| `db_echo` | bool | False |
| `redis_url` | str | redis://localhost:6379/0 |
| `gemini_api_key` | SecretStr \| None | None |
| `storage_backend` | str (M02 turns it into an enum) | "local" |
| `s3_bucket`, `s3_region` | str \| None | None |
| `s3_access_key`, `s3_secret_key` | SecretStr \| None | None |
| `image_provider` | str (M06 turns it into an enum) | "wikimedia" |
| `unsplash_access_key`, `pexels_api_key` | SecretStr \| None | None |
| `max_audio_mb` / `max_video_mb` / `max_image_mb` / `max_cooking_images` | int | 50 / 500 / 10 / 20 |

Production validation: rejects `"*"` in `cors_origins`, and requires `DATABASE_URL` to be set **explicitly** (checked with `model_fields_set`). AI and third-party keys are **not** required at boot.

### Errors — `app/core/errors.py`
```python
class ErrorCode(StrEnum): VALIDATION_ERROR, NOT_FOUND, CONFLICT, UNSUPPORTED_MEDIA, FILE_TOO_LARGE,
    EMPTY_UPLOAD, CORRUPTED_MEDIA, CONFIGURATION_ERROR, RATE_LIMITED, UNAUTHORIZED,
    RECIPE_PROCESSING_FAILED, HTTP_ERROR, INTERNAL_ERROR
class AppError(Exception):  # __init__(message, *, code=None, http_status=None, details=None)
class NotFoundError(AppError)        # 404 NOT_FOUND
class ConflictError(AppError)        # 409 CONFLICT
class ConfigurationError(AppError)   # 503 CONFIGURATION_ERROR
class MediaValidationError(AppError) # __init__(message, *, code=UNSUPPORTED_MEDIA, details=None)
    # status from code: UNSUPPORTED_MEDIA 415, FILE_TOO_LARGE 413, EMPTY_UPLOAD 422,
    # CORRUPTED_MEDIA 422, VALIDATION_ERROR 422
class ErrorResponse(BaseModel): error: ErrorBody(code, message, details?)  # use in OpenAPI `responses=`
def error_response(http_status, code, message, details=None) -> JSONResponse
def register_exception_handlers(app) -> None
```
Envelope: `{"error": {"code": "...", "message": "...", "details": ...?}}` (`details` is left out when it's None).
- `RequestValidationError` → 422 `VALIDATION_ERROR` with `details=[{"field": "body.count", "message": ...}]`.
- Starlette HTTP errors are mapped: 401 → UNAUTHORIZED, 404 → NOT_FOUND, 409 → CONFLICT, 429 → RATE_LIMITED, anything else → `HTTP_ERROR`.
- Unhandled exceptions → 500 `INTERNAL_ERROR` with the message "An unexpected error occurred."; the traceback is logged server-side only.

### Logging — `app/core/logging.py`
```python
def configure_logging(settings) -> None     # root handler: JSON (prod) / text (dev) + filters
def redact(text: str, secrets: Iterable[str] = ()) -> str
class RedactionFilter(logging.Filter)       # masks secrets in msg, str extras and exc_text
class RequestContextFilter(logging.Filter)  # adds record.request_id
class RequestLoggingMiddleware              # pure ASGI; logs method, path (never the query), status, duration_ms
request_id_var: ContextVar[str | None]
```
Structured fields go through `logger.info("event_name", extra={...})`. The `X-Request-ID` header from the client is accepted only if it matches `^[A-Za-z0-9-]{8,64}$`; otherwise a new id is generated.

### Database — `app/db/`
```python
class Base(AsyncAttrs, DeclarativeBase)  # constraint naming convention in NAMING_CONVENTION
class UUIDPrimaryKeyMixin  # id: uuid, default uuid4, server_default gen_random_uuid()
class CreatedAtMixin; class TimestampMixin(CreatedAtMixin)  # created_at / updated_at (timestamptz)
def pg_enum(enum_cls, name) -> sa.Enum   # stores enum VALUES
def create_engine(settings, database_url=None) -> AsyncEngine
def create_sessionmaker(engine) -> async_sessionmaker[AsyncSession]   # expire_on_commit=False
def get_engine() / get_sessionmaker()    # lru_cache'd process-wide
async def get_session() -> AsyncIterator[AsyncSession]   # FastAPI dependency (no auto-commit)
async with session_scope() as session:   # worker/scripts: commits on success, rolls back on error
```

### Enums — `app/models/enums.py` (the PG type name is in brackets)
- `RecipeStatus` [recipe_status]: UPLOADED, QUEUED, PROCESSING, TRANSCRIBING, EXTRACTING, FETCHING_IMAGES, MATCHING_IMAGES, GENERATING_BLOG, COMPLETED, FAILED
- `JobStatus` [job_status]: QUEUED, RUNNING, COMPLETED, FAILED
- `JobStep` [job_step]: UPLOADED, QUEUED, PROCESSING, TRANSCRIBING, EXTRACTING, FETCHING_IMAGES, MATCHING_IMAGES, GENERATING_BLOG, COMPLETED (no FAILED; failure is `JobStatus.FAILED`)
- `MediaType` [media_type]: audio, video, hero_image, cooking_image, ingredient_image
- `Language` [language]: auto, en, bn, hi
- `BlogStatus` [blog_status]: DRAFT, PUBLISHED
- `StepImageStatus` [step_image_status]: MATCHED, UNMATCHED, MANUAL

### Tables (migration revision `0001`)
| Table | Columns beyond SPEC §8 / renames | Constraints |
|---|---|---|
| `recipes` | + `detected_language`, `cuisine`, `category`, `keywords` text[] (default `{}`), `hero_media_id` → media_assets (SET NULL), `published_at`, `owner_id` | `uq_recipes_slug` (slug nullable), `ix_recipes_status`, `ix_recipes_owner_id` |
| `ingredients` | `order` → **`position`**; + `normalized_name` (NOT NULL; Python default = `name.strip().lower()`) | **`uq_ingredients_recipe_id_position`** |
| `recipe_steps` | — | **`uq_recipe_steps_recipe_id_step_number`** |
| `cooking_suggestions` | `order` → **`position`** | **`uq_cooking_suggestions_recipe_id_position`** |
| `media_assets` | `url` → **`storage_key`** (unique); `metadata` column mapped as attribute **`meta`** (JSONB); + `original_filename`, `size_bytes`, `position`, `created_at` | `uq_media_assets_storage_key`, `ix_media_assets_recipe_id_type` |
| `step_images` | `step_id` nullable (SET NULL); + `status` (default UNMATCHED), `reason` | **`uq_step_images_media_asset_id`** |
| `ingredient_images` | + `provider` (NOT NULL), `alt_text` | **`uq_ingredient_images_ingredient_id`** |
| `blogs` | + `status` (default DRAFT), `primary_keyword`, `secondary_keywords` text[], `og_title`, `og_description`, `hero_alt_text`, `json_ld` JSONB, `faq` JSONB, `published_at`; `slug` NOT NULL | **`uq_blogs_recipe_id`**, **`uq_blogs_slug`** |
| `jobs` | `current_step` is a JobStep (default UPLOADED); `progress` int default 0; + `error_code`, `attempts` (default 0), `celery_task_id` | `ck_jobs_progress_range` (0–100), `ix_jobs_status`, `ix_jobs_recipe_id` |

Every child FK to `recipes.id` is `ON DELETE CASCADE`. ORM relationships on `Recipe` (`ingredients`, `steps`, `suggestions`, `media_assets`, `step_images`, `ingredient_images`, `blog`, `jobs`) use `cascade="all, delete-orphan", passive_deletes=True`. `Recipe.hero_media` uses `post_update=True`. Collections are ordered by `position` / `step_number`.

### Endpoints
| Method | Path | Response | Codes |
|---|---|---|---|
| GET | `/api/v1/health` | `HealthResponse{status: ok\|degraded, version, database: ok\|error}` | 200, 503 |

OpenAPI is at **`/openapi.json`**, with docs at `/docs` and `/redoc`. Routers are mounted under `API_V1_PREFIX = "/api/v1"` through `app/api/v1/router.py::api_router`.

## 5. Contract changes to earlier modules
- None (first module).

## 6. Design decisions & deviations from SPEC
- **Dev Postgres is on host port 5434**, because 5432 is taken by a local Postgres and 5433 by another project's container on this machine. The container port is still 5432.
- The column names `order` → `position` and `url` → `storage_key` were renamed as the module prompt specified. `order` is a reserved SQL word, and storing keys rather than URLs keeps storage backend-agnostic (SPEC §7).
- Added `ErrorCode.HTTP_ERROR` for Starlette HTTP errors without a specific mapping (for example 405). It wasn't in the prompt's list, but it avoids mislabelling those responses.
- `JobStep` leaves out FAILED; the failed state is carried by `JobStatus.FAILED`, and `current_step` keeps showing the step that failed.
- `normalized_name` gets a context-sensitive Python default taken from `name`, so rows inserted without it stay valid. M05's normalize node will set it explicitly.
- Relationships use default lazy loading. With async SQLAlchemy, **services must eager-load explicitly** (`selectinload(...)`), or accessing the relationship raises `MissingGreenlet`.
- The health endpoint returns **503** when the DB is down, which makes it usable as a readiness probe.
- The migration is hand-written from the autogenerate draft. Enums are created explicitly (`language` is shared by two columns), and the circular `recipes.hero_media_id` FK is added after `media_assets` exists. `alembic check` shows no drift.
- Library versions resolved: FastAPI 0.141, Starlette 1.7, **SQLAlchemy 2.1.0**, Pydantic 2.13, pydantic-settings 2.15, Alembic 1.20, pytest 9.1, pytest-asyncio 1.4, ruff 0.16, mypy 2.3. Starlette 1.x deprecates `HTTP_413_REQUEST_ENTITY_TOO_LARGE` and `HTTP_422_UNPROCESSABLE_ENTITY`; use **`HTTP_413_CONTENT_TOO_LARGE`** and **`HTTP_422_UNPROCESSABLE_CONTENT`**.
- Python 3.13.5 was used (it satisfies `>=3.12`).

## 7. Test results
### Baseline (before changes)
```
N/A — first module, empty repository.
```
### Module unit tests
```
> uv run pytest -q -m unit
29 passed, 15 deselected in 0.37s
```
### Integration tests (real PostgreSQL 16 via docker-compose.dev.yml)
```
> uv run pytest -q -m integration
15 passed, 29 deselected in 3.92s
```
They cover: the migration round trip (tables and enums are created, then fully dropped including the PG enum types), `alembic check` showing no drift, defaults, the full-graph insert plus cascade delete, every unique constraint (ingredient position, step number, blog slug, blog per recipe, ingredient image, step image per photo), the progress check constraint, health reporting `database: ok`, and the OpenAPI summary and description check across every `/api/v1` operation.

One failure during development: `test_defaults_are_applied` hit `MissingGreenlet`, because `refresh()` expired a relationship that was then lazy-loaded. The test was fixed (see the note on eager loading in §6); it wasn't a product bug.

### Full regression + lint + types
```
ruff check .            -> All checks passed!
ruff format --check .   -> 28 files already formatted
mypy app (strict)       -> Success: no issues found in 19 source files
pytest -q               -> 44 passed in 4.19s
alembic (dev DB): upgrade head -> exit 0; downgrade base -> exit 0; upgrade head -> exit 0
alembic check           -> No new upgrade operations detected.
boot smoke: uvicorn app.main:app --port 8011
  GET /api/v1/health -> 200 {"status":"ok","version":"0.1.0","database":"ok"} (X-Request-ID set)
  GET /docs -> 200
frontend: N/A (M09)
```

## 8. Known issues
| Severity | Issue | Suggested fix / owner module |
|---|---|---|
| non-blocking | **FFmpeg is not installed** on the dev machine; M02 needs it. | M02: `winget install Gyan.FFmpeg` (or choco), then restart the shell |
| non-blocking | Starlette's `ServerErrorMiddleware` sits outside `RequestLoggingMiddleware`, so an unhandled-500 response has no `X-Request-ID` header (the access log still records status 500). | M11 hardening, if needed |
| non-blocking | `ConfigurationError` defaults to 503. Callers can override it with `http_status=` when they need a different status. | — |

## 9. Notes for the next module
- **Start the services:** from the repo root, `docker compose -f docker-compose.dev.yml up -d`. Postgres is at `localhost:5434` (user, password and DB all `recipebook`, plus the test DB `recipebook_test`). Redis is at `localhost:6379`.
- **Run commands from `backend/`**: `uv run pytest`, `uv run alembic ...`, `uv run ruff ...`, `uv run mypy app`. In PowerShell, alembic writes INFO to stderr, so wrapping `2>&1` makes it *look* like an error; check the exit code instead.
- **Fixtures to reuse** (`backend/tests/conftest.py`):
  - `settings`: session-scoped `Settings(app_env=TEST)`.
  - `alembic_config`, and `make_alembic_config(url)` for building an Alembic `Config` against a URL.
  - `migrated_database`: session-scoped; runs `alembic upgrade head` on `TEST_DATABASE_URL`.
  - `db_session`: an `AsyncSession` inside an outer transaction that is always rolled back. Code under test **may** call `commit()`, which only releases a savepoint.
  - `app` is `create_app(settings)`. `db_app` is the same app with `get_session` overridden to `db_session`.
  - `client`: `httpx.AsyncClient` over ASGI, bound to `db_app`.
  - For testing 500s, use `ASGITransport(app=..., raise_app_exceptions=False)`.
- Mark tests with `pytestmark = pytest.mark.unit` or `pytest.mark.integration`. The `requires_ffmpeg` and `e2e` markers are already registered.
- `create_app()` calls `configure_logging()`, which **replaces the root handlers**. When testing log output, use the filters and formatters directly (as `test_logging.py` does) rather than `caplog` across `create_app`.
- New routers: add them in `app/api/v1/router.py`. Every operation needs `summary`, `description`, `response_model`, and `responses={4xx: {"model": ErrorResponse}}`, because `test_every_api_operation_has_summary_and_description` enforces the summary and description.
- New settings: add a field to `Settings` **and** a commented line to `/.env.example`.
- New tables or columns: change the models, run `uv run alembic revision --autogenerate -m "..." --rev-id 0002`, **review the file by hand**, then run the round trip and `alembic check`.

## 10. README notes
- **Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker (for Postgres and Redis), and FFmpeg (from M02).
- **Local backend setup:**
  ```bash
  docker compose -f docker-compose.dev.yml up -d
  cp .env.example .env          # PowerShell: Copy-Item .env.example .env
  cd backend
  uv sync
  uv run alembic upgrade head
  uv run uvicorn app.main:app --reload
  # http://localhost:8000/docs
  ```
- **Tests:** `uv run pytest` (all), `uv run pytest -m unit`, `uv run pytest -m integration` (needs the dev compose stack).
- **Lint and types:** `uv run ruff check . && uv run ruff format --check . && uv run mypy app`.
- **Migrations:** `uv run alembic upgrade head`, `uv run alembic downgrade -1`, `uv run alembic revision --autogenerate -m "msg"` (always review the result), and `uv run alembic check` (drift check).
- **Error format:** every API error is returned as `{"error": {"code", "message", "details?"}}`.
