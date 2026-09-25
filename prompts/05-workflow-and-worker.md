# Prompt 05 — LangGraph Workflow Core + Celery Worker + Processing API

**Depends on:** M01–M04. **SPEC:** §3, §4, §9, §10, §11, §32, §33, §34.

## Context intake
1. Follow `prompts/00-conventions.md` §A.
2. Read the reports for M01–M04. Open `app/models/*`, `app/services/recipe_service.py`, `app/services/job_service.py`, `app/services/media_service.py` (`select_transcription_source`), `app/services/media_processing.py`, `app/ai/provider.py`, `app/ai/fake.py`, `app/ai/validation.py`, and the `on_recipe_created` hook from M03.
3. Run the baseline and make sure it's green.

## Goal
Build the full SPEC §10 graph **topology** with the core nodes implemented for real: validate, prepare media, transcribe, extract, normalize, and save. The nodes that later modules own exist as **explicit pass-through stubs**. Each stub has one line, `# implemented in M06/M07/M08`, returns `{}`, and has its own test asserting it's a no-op. Add Celery + Redis execution, job progress, retries, and the `/process` endpoint.

## Build

### 1. State — `app/ai/workflows/state.py`
The SPEC §11 `RecipeGraphState` (a TypedDict, `total=False`). It contains **only** primitives, UUIDs, and Pydantic models: `recipe_id`, `job_id`, `language_hint`, `transcription_source_key`, `needs_audio_extraction`, `audio_key`, `video_key`, `transcript`, `detected_language`, `recipe_data: RecipeExtraction`, `ingredient_images`, `cooking_images`, `matched_images`, `blog`, `seo`, `similar_recipes`, `warnings: list[str]`.
- Define the data classes the later modules fill in (`IngredientImageData`, `CookingImageData`, `StepImageMatch`, `BlogData`, `SimilarRecipe`) **here as minimal Pydantic models**, so the state type is complete. M06, M07, and M08 may extend them, and must record that as a contract change.
- Store storage **keys** in state, never URLs or ORM objects (SPEC §11).

### 2. Dependencies — `app/ai/workflows/deps.py`
- `WorkflowDeps` dataclass: `ai: AIProvider`, `storage: StorageBackend`, `session_factory`, `settings`, and a slot for `image_search` that M06 fills in. Nodes get their dependencies through LangGraph `config["configurable"]["deps"]`, which is simple and explicit, with no globals. Tests inject fakes the same way.

### 3. Nodes — `app/ai/workflows/nodes/` (one file per node, and each node does one thing)
| Node | Responsibility | Job step |
|---|---|---|
| `validate_input` | Load the recipe and media rows (read-only), check that a transcription source exists, then fill `audio_key`/`video_key`/`transcription_source_key` using `select_transcription_source` | PROCESSING |
| `prepare_media` | If `needs_audio_extraction`, run ffmpeg `extract_audio` on the video, store the result as an **internal derived asset** (`meta.derived=true`, reusing an existing derived asset if one is already there, which keeps it idempotent) and set `transcription_source_key` | PROCESSING |
| `transcribe_audio` | `ai.transcribe`. **Skip if `recipe.transcript` is already stored and `force_retranscribe` is false** (this saves cost on retries). Persist the transcript and detected_language right away | TRANSCRIBING |
| `extract_recipe` | `ai.extract_recipe` + the accuracy guard (M04) | EXTRACTING |
| `normalize_recipe` | Deterministic cleanup: trim, dedupe ingredients, set `normalized_name`, renumber steps 1..N, drop empty suggestions. **No LLM** | EXTRACTING |
| `fetch_ingredient_images` | stub (M06) | FETCHING_IMAGES |
| `match_cooking_images` | stub (M06) | MATCHING_IMAGES |
| `generate_blog` | stub (M07) | GENERATING_BLOG |
| `generate_seo_metadata` | stub (M07) | GENERATING_BLOG |
| `find_similar_recipes` | stub (M08) | GENERATING_BLOG |
| `save_result` | Persist the recipe fields, ingredients, steps, and suggestions **idempotently** (below). Set the recipe status to COMPLETED, which means "draft ready for review" and **is not published** (SPEC §46). Job COMPLETED at 100% | COMPLETED |

- The node wrapper `instrumented_node(name, job_step, progress)` is a decorator that sets the job's `current_step`/`progress` and the recipe status in a **short separate transaction** before the node runs. It logs `workflow_node`, `duration_ms`, `status`, `recipe_id`, and `job_id`, and turns exceptions into a typed `WorkflowError` with the failing node attached. This decorator is the one place for progress and logging (no duplicated logic).
- Progress percentages are defined once as a constant table.

### 4. Graph — `app/ai/workflows/graph.py`
- `build_recipe_graph() -> CompiledGraph`: a linear `StateGraph` following SPEC §10 exactly. No checkpointer in v1 (retries re-run the graph, and the nodes are idempotent). Explain why in a comment.
- `async run_recipe_workflow(recipe_id, job_id, deps, *, force=False) -> RecipeGraphState`.

### 5. Idempotency (SPEC §34)
- `save_result` runs inside **one transaction**: it deletes and re-inserts the ingredient, step, and suggestion lists for that recipe (the unique constraints from M01 guarantee no duplicates). Ingredient images and step images (M06) use upserts on their unique keys.
- **Don't clobber user edits:** if the recipe has `user_edited_at` set, reprocessing requires `force=true`, otherwise 409. Add the `user_edited_at` column through a **new Alembic migration**, and have M03's `update_recipe` set it. That's a contract change: record it.
- Running the workflow twice for the same recipe gives the same row counts.

### 6. Worker — `app/workers/celery_app.py`, `app/workers/tasks.py`
- A Celery app configured from settings (`REDIS_URL` as broker and result backend, `task_acks_late=True`, `worker_prefetch_multiplier=1`, JSON serializer, and time limits `WORKFLOW_SOFT_TIME_LIMIT`/`HARD`).
- `process_recipe(job_id: str, force: bool = False)`:
  - Mark the job RUNNING and increment `attempts`.
  - Run `asyncio.run(run_recipe_workflow(...))`.
  - On `AIProviderError(retryable=True)`, `self.retry` with backoff up to `WORKFLOW_MAX_RETRIES`.
  - On final failure, set the job and recipe to FAILED with a **safe** `error_code`/`error` (for example `RECIPE_PROCESSING_FAILED`, "Unable to process the recipe audio."), and log the full detail server-side.
  - **Guard:** if the job is already COMPLETED, or RUNNING under another live task id, exit (duplicate-delivery safety).
- `enqueue_processing(job_id, force)` in `app/services/processing_service.py` is the only place that calls `.delay`. `celery_task_id` is stored on the job.

### 7. API
- `POST /api/v1/recipes/{id}/process` (body: `{force?: bool}`):
  - Creates a **new Job** (or reuses the QUEUED one from upload), enqueues it, and returns **202** `{recipe_id, job_id, status: "queued"}`.
  - Returns 409 if a job is already RUNNING or QUEUED with a live task (unless it's that same queued upload job), or if user edits exist and `force` is false.
  - Rate-limited.
- Wire M03's `on_recipe_created` hook so that when `AUTO_PROCESS_ON_UPLOAD` is true, the upload job is enqueued straight away (SPEC §33 flow). With it off, the client calls `/process`.

## Tests
**Unit**
- Each real node, tested in isolation with `FakeAIProvider`, a tmp `LocalStorage`, and the DB. Transcription is skipped when the transcript exists. Normalize dedupes and renumbers. Each stub node returns `{}`.
- The `instrumented_node` wrapper updates the job step and progress, and on exception marks the failing node and doesn't leak the error text to `job.error`.
- The graph has the exact node order from SPEC §10 (inspect `graph.get_graph().nodes`/edges).

**Integration — API + DB + storage + ffmpeg + AI(fake) + graph + Celery**
- Configure Celery `task_always_eager=True` (and `task_eager_propagates`) in the test settings.
- Scenario A: `POST /recipes` (audio), then auto-enqueue, then the workflow completes. `GET /jobs/{id}` is COMPLETED at 100%. `GET /recipes/{id}` has the fake transcript, detected_language `bn`, 6 ingredients (one with a null quantity and the note), and 4 steps. Recipe status is COMPLETED and **the blog isn't published**.
- Scenario B: video only, so the derived audio asset is created and transcription uses it. Scenario C: audio + video, so fake `transcribe` is called **exactly once**, with the audio key.
- Retry and idempotency: fake `extract_recipe` raises a retryable error on the first call and succeeds on the second. The final state is COMPLETED with **no duplicate rows**. Then run `/process` with `force=true` twice and check the row counts are unchanged.
- Non-retryable failure: the job is FAILED, `error_code=RECIPE_PROCESSING_FAILED`, the message is generic, and the logs contain the node name.
- User edits: `PATCH` a recipe and then `/process` without force gives 409, and with force gives 202.
- `/process` while RUNNING gives 409.
- **Real-worker smoke** (marked `integration`, skipped if Redis is unreachable): start a Celery worker in a subprocess against the dev Redis, run `process_recipe` for real with `AI_PROVIDER=fake`, and poll `/jobs/{id}` until COMPLETED (with a timeout).

## Acceptance
Full regression, including the M01–M04 tests, and the migration round trip including the new revision.

## Handoff
Write `docs/modules/M05-report.md`. Contracts: the state keys and types, `WorkflowDeps`, the node names and file paths, the stub nodes and which module owns each, `instrumented_node`, the progress table, `run_recipe_workflow`, `process_recipe`, `enqueue_processing`, the `/process` API, the new migration revision, `user_edited_at` semantics, the Celery settings, how to run the worker locally (including a **Windows note**: Celery needs `--pool=solo` on Windows), and the eager-mode fixture name. Update `PROGRESS.md`.
