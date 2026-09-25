# Prompt 03 — Recipe Upload & CRUD API

**Depends on:** M01, M02. **SPEC:** §6, §23, §26, §30, §31, §39, §46.

## Context intake
1. Follow `prompts/00-conventions.md` §A.
2. Read `docs/modules/M01-report.md` and `M02-report.md`. Open `app/main.py`, `app/db/session.py`, `app/models/*`, `app/services/media_validation.py`, `app/services/media_service.py`, `app/integrations/storage/*`, and the shared fixtures.
3. Run the baseline and make sure it's green.

## Goal
The REST surface for creating a recipe from uploads, reading it, editing the draft, and reading job status. It also adds the auth, rate-limit, and secure-media architecture. **Processing is not triggered here** (M05 adds `POST /recipes/{id}/process`). **No AI calls.**

## Build

### 1. Schemas — `app/schemas/`
- `recipe.py`: `IngredientOut/In`, `RecipeStepOut/In`, `SuggestionOut/In`, `MediaAssetOut` (id, type, mime, url, position, meta subset; **url** comes from the media route or presigned URL, never a storage key), `StepImageOut`, `IngredientImageOut`, `RecipeOut` (every recipe field + children + media + `latest_job`), `RecipeCreateResponse` (`recipe_id`, `job_id`, `status`), and `RecipeUpdate` (every field optional).
  - For ingredients, steps, and suggestions in `RecipeUpdate`, a supplied list means **replace the full list** (simple and idempotent). Write this in the OpenAPI description.
- `job.py`: `JobOut` (id, recipe_id, status, current_step, progress, error_code, error, created_at, updated_at, plus `steps: list[JobStepProgress]` computed from `current_step` so the UI can render the checklist in SPEC §24).
- Pydantic validation: step numbers unique and contiguous after normalization, positions set server-side, trimmed strings, and max lengths.

### 2. Services — `app/services/recipe_service.py`, `job_service.py`
- `create_recipe_from_upload(session, storage, *, language, audio, video, hero, cooking_images, owner_id) -> (Recipe, Job)`:
  1. `validate_submission`
  2. validate each file
  3. create a `Recipe(status=UPLOADED)`
  4. store the media (cooking photos keep their upload `position`, and the hero sets `hero_media_id`)
  5. run `ensure_decodable` for audio and video (probe errors become 422 `CORRUPTED_MEDIA`)
  6. create `Job(status=QUEUED, current_step=UPLOADED)`
  7. commit
  - If anything fails, **delete any stored files** (compensating cleanup) and roll back.
- `get_recipe`, `update_recipe` (replace-lists semantics inside one transaction; rejects edits while a job is RUNNING with 409 `CONFLICT`), and `list_recipes` (paginated, owner-scoped).
- `get_job`, and `get_latest_job(recipe_id)`.

### 3. Security — `app/core/security.py`
- `Principal` dataclass (`id`, `is_anonymous`). `get_current_principal` dependency with `AUTH_MODE` setting (enum `none | api_key`):
  - `none` (dev default): a fixed dev principal.
  - `api_key`: `Authorization: Bearer <token>` compared in constant time against `API_AUTH_TOKENS` (SecretStr list), which is **server-to-server/admin only**. Document in the report that browser users need a real identity provider (OIDC/session cookie) in production, and that the dependency is the single seam where it plugs in. **Never put an API token in the frontend.**
- Ownership: recipe endpoints check `recipe.owner_id == principal.id`, otherwise 404 (don't leak that the recipe exists).
- Rate limiting: `slowapi` with Redis storage (`REDIS_URL`), and in-memory in tests. Limits live in settings: upload `RATE_LIMIT_UPLOAD` (e.g. `10/hour`), everything else `RATE_LIMIT_DEFAULT`. A 429 comes back in the standard error envelope as `RATE_LIMITED`.
- Upload size is enforced by the streaming validation (M02). Also set a global request body limit (middleware) a bit above the largest allowed file set.

### 4. Media delivery — `app/api/v1/media.py`
- `GET /api/v1/media/{asset_id}`: access is checked (owner, **or** the recipe has been published, which M07 sets). For local storage it streams with **Range** support so `<audio>`/`<video>` can seek. For S3 it returns 307 to a short-lived presigned URL. Set `Cache-Control` correctly (private vs public).
- `media_url_for(asset) -> str` is the single function every schema uses to build URLs (built from `PUBLIC_BASE_URL`). Private URLs are never logged.

### 5. Endpoints — `app/api/v1/recipes.py`, `jobs.py`
| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/recipes` | `multipart/form-data`: `language` (enum, default auto), `audio?`, `video?`, `hero_image?`, `cooking_images[]?`. Returns **202** `RecipeCreateResponse` with `status: "queued"`. Errors: 400/413/415/422/429. |
| GET | `/api/v1/recipes` | Paginated list (owner). |
| GET | `/api/v1/recipes/{id}` | `RecipeOut`. 404. |
| PATCH | `/api/v1/recipes/{id}` | `RecipeUpdate` → `RecipeOut`. 404/409/422. |
| GET | `/api/v1/jobs/{id}` | `JobOut`. 404. |
| GET | `/api/v1/media/{asset_id}` | See §4. |

Every endpoint has `summary`, `description`, `response_model`, and `responses={...: {"model": ErrorResponse}}` (SPEC §39).

Note: SPEC §6 says the job is created on upload. Enqueueing happens in M05, either when `POST /process` is called or through an auto-enqueue setting (`AUTO_PROCESS_ON_UPLOAD`, default true, which M05 wires). For now, leave a clearly marked hook in `create_recipe_from_upload` that M05 fills in: `on_recipe_created(recipe_id, job_id)`, which does nothing by default.

## Tests
**Unit**
- Schema validation: step renumbering, max lengths, and the replace-list semantics.
- `JobOut.steps` computation for each `current_step`.
- Principal resolution: none mode, a valid token, an invalid token (401 envelope), and a constant-time compare being used.
- `media_url_for` never exposes the storage key.

**Integration — HTTP + DB + storage + validation (real Postgres, LocalStorage in tmp, ffmpeg fixtures from M02)**
- `POST /recipes` with audio only → 202. DB has the recipe (UPLOADED), 1 audio MediaAsset, and the job (QUEUED). The file exists in storage.
- With video only; with audio + video + hero + 3 cooking photos (checks positions, and that `hero_media_id` is set).
- Rejections: no files (422 `VALIDATION_ERROR`/`EMPTY_UPLOAD`); a renamed PNG sent as audio (415); an oversize file using a lowered limit via settings override (413, and **no leftover file in storage**); a corrupted mp4 (422 `CORRUPTED_MEDIA`, with no rows left behind); 21 cooking photos (422).
- `GET /recipes/{id}` shape matches `RecipeOut`, and media URLs point at `/api/v1/media/...`.
- `PATCH /recipes/{id}` replaces ingredients and steps. A duplicate step number gives 422. Editing while the job is RUNNING gives 409.
- `GET /jobs/{id}` returns QUEUED with the step checklist.
- `GET /media/{id}`: a Range request returns 206 with the correct bytes. Another principal (api_key mode with a second token) gets 404.
- Rate limit: the (N+1)th upload in the window gives 429 `RATE_LIMITED`.
- OpenAPI: every `/api/v1` operation has a summary and a response model (loop over `app.openapi()`).

## Acceptance
Full regression (conventions §E), with M01 and M02 tests still green.

## Handoff
Write `docs/modules/M03-report.md`. Contracts: every endpoint with its request and response schema and status codes, the service function signatures, `Principal`/`get_current_principal`, `media_url_for`, the `on_recipe_created` hook, the settings added (`AUTH_MODE`, `API_AUTH_TOKENS`, `RATE_LIMIT_*`, `AUTO_PROCESS_ON_UPLOAD`), and the HTTP test client fixture names. Put example `curl` calls under "README notes". Update `PROGRESS.md`.
