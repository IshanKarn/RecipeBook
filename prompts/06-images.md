# Prompt 06 — Ingredient Image Search + Cooking-Photo Step Matching

**Depends on:** M02, M04, M05 (and M03 for the API). **SPEC:** §14, §15, §16, §23, §34, §45.

## Context intake
1. Follow `prompts/00-conventions.md` §A.
2. Read the reports for M02–M05. Open `app/ai/workflows/state.py`, `deps.py`, `graph.py`, the stub nodes `fetch_ingredient_images.py` and `match_cooking_images.py`, `app/ai/provider.py` (`match_image_to_steps`), `app/ai/fake.py` (filename match rule), `app/models/media.py`, and `app/schemas/recipe.py`.
3. Run the baseline and make sure it's green.

## Goal
Replace the two M05 stubs with real implementations. Add the image-search integrations (real images only, with licence and attribution), Gemini-vision step matching with a confidence threshold, and an API for manual reassignment.

## Build

### 1. Image search — `app/integrations/image_search/`
- `base.py`: `ImageSearchProvider` Protocol with `async search(query: str, *, limit: int) -> list[ImageCandidate]`. `ImageCandidate` holds `image_url`, `thumbnail_url`, `source_url` (the page), `width`, `height`, `license`, `license_url`, `attribution` (author + provider text), `provider`, and `title`.
- `wikimedia.py` (the default, no key needed): the Commons API (`action=query&generator=search&gsrnamespace=6&prop=imageinfo&iiprop=url|extmetadata&iiurlwidth=...`). Parse `LicenseShortName`, `Artist` (**strip the HTML** from the artist field), `LicenseUrl`, and `AttributionRequired`. **Only accept free licences**: an allowlist (CC0, Public domain, CC BY, CC BY-SA). Send a descriptive `User-Agent` as Wikimedia's policy requires, set through the `IMAGE_SEARCH_USER_AGENT` setting.
- `unsplash.py` / `pexels.py`: keys from settings, `ConfigurationError` when they're missing. Use their required attribution format ("Photo by X on Unsplash", with the links). Unsplash guidelines require **hotlinking** their URLs and triggering the download endpoint when used; implement that trigger, or document clearly why it's omitted.
- A shared `httpx.AsyncClient` with timeouts, a small concurrency limit (a semaphore), and 429/5xx retry with backoff. **Don't download or re-host images** (SPEC §14): only URLs are stored.
- `get_image_search_provider(settings)` picks from `IMAGE_PROVIDER` (enum). Optional fallback chain `IMAGE_PROVIDER_FALLBACKS` (for example `wikimedia,pexels`), skipping any provider that isn't configured.

### 2. Ingredient image service — `app/services/ingredient_image_service.py`
- `build_query(ingredient) -> str`: uses the English/normalized name. Bengali or Hindi names use the English term the extractor stored in `notes`/`normalized_name`, plus a food hint such as "raw", "ingredient", or "food". Keep it deterministic.
- `select_best(candidates, ingredient) -> ImageCandidate | None`: a deterministic score. It checks that the licence is allowed, that the title or description matches the tokens, that the aspect ratio is reasonable, that the resolution is at least a minimum, and it penalises diagrams, logos, and SVG/maps. Candidates below the threshold give `None`. **Never invent a result.**
- `alt_text_for(ingredient, candidate) -> str`, for example "Raw potatoes (aloo)". It must be meaningful (SPEC §45).
- A cache: before searching, reuse an existing `IngredientImage` from **another** recipe with the same `normalized_name` and provider (no extra API calls). Keep it simple, as a DB lookup.

### 3. Node `fetch_ingredient_images`
For each normalized ingredient (with bounded concurrency), search, select, and put an `IngredientImageData` into state. Failures for a single ingredient become **warnings, not a workflow failure**. The graph carries on without that image.

### 4. Node `match_cooking_images`
- Load the cooking-photo assets (ordered by position). For each one, call `ai.match_image_to_steps(ImageInput(local_path, mime), steps, context)`.
- Threshold `IMAGE_MATCH_MIN_CONFIDENCE` (default 0.6). Below it, or with `step_number=None` or a step number that doesn't exist, the photo is `UNMATCHED` with `step_id=None`. **Don't force a match** (SPEC §15).
- Two photos may match the same step (keep both, ordered by position). The final-dish detection is optional: if no hero was uploaded and the AI reports "final dish" with high confidence, that photo becomes a **suggested** hero (`meta.suggested_hero=true`). The user confirms it in the editor; it's never set automatically.
- Store the AI's `description` as the photo's alt text in `meta.alt_text`.
- SPEC §16: if there's no hero and no suggested hero, **don't generate one**. The blog (M07) handles a missing hero gracefully.

### 5. Persisting (in `save_result`, extending M05)
- Ingredient images: upsert on `ingredient_images.ingredient_id`. The ingredient lists get re-inserted on reprocess, so map by `position` or `normalized_name` **after** the ingredients are inserted, inside the same transaction.
- Step images: upsert on `step_images.media_asset_id`. **Rows with `status=MANUAL` are never overwritten** by reprocessing.
- Record every change to `save_result` as a contract change.

### 6. Manual assignment API (SPEC §15, §23)
- `PUT /api/v1/recipes/{id}/step-images/{media_asset_id}` with body `{step_number: int | null}`. It sets `MANUAL` (or `UNMATCHED` when null), validates that the step exists, and returns `StepImageOut`. 404/422.
- `PUT /api/v1/recipes/{id}/hero` with body `{media_asset_id: UUID | null}`. The asset must belong to the recipe and be of type `hero_image` or `cooking_image`.
- `DELETE /api/v1/recipes/{id}/ingredient-images/{ingredient_id}` lets the user reject a bad image, and `POST .../ingredient-images/{ingredient_id}/refresh` re-runs the search for one ingredient synchronously, with a short timeout and rate limiting.
- Full OpenAPI metadata. Extend `RecipeOut` so it exposes the step images grouped by step, unmatched photos, and ingredient images **with attribution** (a contract change to M03: record it).

## Tests
**Unit**
- Wikimedia response parsing: use a recorded JSON fixture under `tests/fixtures/wikimedia/` **written by hand or trimmed**, rather than fetched live during the tests. Check licence allowlisting, stripping the HTML from the artist field, and that non-free licences are rejected.
- Unsplash and Pexels parsing, and their attribution formats. A missing key gives `ConfigurationError`. The fallback chain skips unconfigured providers.
- `build_query` for en/bn/hi ingredients, `select_best` scoring (including returning `None` when nothing qualifies), and `alt_text_for`.
- Matching logic: threshold edges (0.59 is unmatched, 0.6 is matched), a nonexistent step number is unmatched, two photos can land on the same step, and the suggested hero is never auto-applied.

**Integration — graph + DB + API (respx-mocked image APIs, FakeAIProvider)**
- Full workflow with audio + 3 cooking photos (`step1_*.jpg`, `step3_*.jpg`, `random_*.jpg` following the M04 fake rule) + mocked Wikimedia:
  - `RecipeOut` shows ingredient images with licence and attribution for the matchable ingredients, and none for the unmatched fixture ingredient.
  - Photos map to steps 1 and 3, and one is unmatched.
- **Idempotency:** a Wikimedia 500 for one ingredient on the first run gives a warning (and the job still completes). `/process force=true` then gives exactly one `IngredientImage` per ingredient and no duplicate `StepImage`.
- Manual assignment: assign the unmatched photo to step 2 (MANUAL), reprocess with force, and the MANUAL assignment survives. Setting and clearing the hero works. A foreign asset id gives 404.
- The cache: a second recipe with the same ingredient makes no new HTTP call (respx call count).
- No image bytes were downloaded (respx: only search-API routes were called, never the image URLs).

## Acceptance
Full regression. Every earlier test stays green, including the M05 workflow tests with the updated stubs.

## Handoff
Write `docs/modules/M06-report.md`. Contracts: `ImageSearchProvider`, `ImageCandidate`, the provider selection and fallback, the service functions, the node behaviour, the threshold setting, the new endpoints, the `RecipeOut` changes, the `save_result` changes, and the alt-text sources (needed by M07's blog). Add attribution-compliance notes under "README notes". Update `PROGRESS.md`.
