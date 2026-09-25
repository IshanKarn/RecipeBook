# Prompt 08 — Similar Recipes

**Depends on:** M05, M07 (and M01 models). **SPEC:** §19, §22, §26, §47.

## Context intake
1. Follow `prompts/00-conventions.md` §A.
2. Read the reports for M05 and M07 (and skim M01 for the columns: `ingredients.normalized_name`, `recipes.cuisine/category/keywords`). Open the stub `find_similar_recipes.py`, `state.py` (`SimilarRecipe`), `render_blog_html`, and `PublicBlogOut`.
3. Run the baseline and make sure it's green.

## Goal
Deterministic, PostgreSQL-only similar-recipe recommendations, with no vector DB (SPEC §22, §47). They're exposed through an API, included in the public blog, and computed as the last graph node before save.

## Build

### 1. Migration
- Enable `pg_trgm`, add a GIN trigram index on `recipes.dish_name`, a GIN index on `recipes.keywords`, and a btree index on `ingredients.normalized_name`. `downgrade` reverses all of it. If the extension can't be created (managed-DB permissions), the code must **degrade** to ILIKE matching. Detect this once at startup and log it.

### 2. `app/services/similarity_service.py`
- `async find_similar(session, recipe_id, *, limit=3, published_only=True) -> list[SimilarRecipeOut]`
- The score is a documented weighted sum, calculated **in SQL** (one query with CTEs, readable and commented):
  - `0.45 × ingredient Jaccard` (over `normalized_name` sets, ignoring a stop-list of pantry staples like salt, water, oil, and sugar, defined as a constant)
  - `+ 0.25 × similarity(dish_name)` (pg_trgm)
  - `+ 0.15 × (cuisine match)`
  - `+ 0.10 × (category match)`
  - `+ 0.05 × keyword overlap ratio`
- The weights are constants in one place. Excluded: the recipe itself, unpublished recipes (when `published_only`), and anything scoring below `SIMILARITY_MIN_SCORE`. Deterministic tie-break: `published_at desc, id`.
- `SimilarRecipeOut`: `recipe_id`, `slug`, `title`, `dish_name`, `hero_image_url` (or null), `score`, `shared_ingredients: list[str]` (≤5).
- **Embeddings-ready seam:** a `SimilarityStrategy` Protocol with a single implementation, `SqlSimilarity`, plus a comment that says where an embedding strategy would go. Don't add more than that (SPEC §47).

### 3. Node `find_similar_recipes` (replaces the M05 stub)
Calls the service with `published_only=True`, puts the IDs and scores into `state["similar_recipes"]`, and treats a failure as a warning. **Don't persist the results.** They go stale as new recipes are published, so the API computes them at read time. The node's output is only used for logging and as a sanity check. Document this decision. If you'd rather drop the node from the graph, **don't**: SPEC §10 lists it. Keep it and keep it cheap.

### 4. API and blog
- `GET /api/v1/recipes/{id}/similar?limit=3` (owner or published) returns `list[SimilarRecipeOut]`, with full OpenAPI metadata.
- `PublicBlogOut` gains `similar_recipes` (computed at read time and cached briefly in Redis, keyed by recipe id with a TTL of `SIMILAR_CACHE_TTL`; invalidated when that recipe is published or unpublished). The rendered HTML resolves the similar placeholder into a semantic "You may also like" `<section>` of cards (`<article><a><img alt><h3>`) that works without JS.

## Tests
**Unit**
- The score function in isolation: seed rows and assert the ranking is the expected order. The staple stop-list is ignored. Self and unpublished recipes are excluded. Tie-break order holds. The minimum score threshold works.
- The ILIKE fallback path gives a sensible order when the trigram path is disabled.

**Integration — graph + DB + blog API**
- Seed 5 published recipes through the **real workflow** (FakeAIProvider variants: add a fake recipe-variant option, for example `FakeAIProvider(variant="dal")`), with overlapping ingredients and cuisines, then publish them.
  - `GET /recipes/{id}/similar` returns the expected top 3 in order, with `shared_ingredients`.
  - The public blog `GET /blog/{slug}` includes `similar_recipes`, and its HTML has the "You may also like" section with links to `/blog/{slug}`.
- Unpublishing a recipe removes it from the others' similar lists (cache invalidation works).
- The graph still completes when the similarity query raises (the warning path).
- Migration round trip with `pg_trgm`.

## Acceptance
Full regression.

## Handoff
Write `docs/modules/M08-report.md`. Contracts: `find_similar`, `SimilarRecipeOut`, the weights table, the stop-list, the endpoint, the `PublicBlogOut` change, the caching behaviour, and the migration revision. Update `PROGRESS.md`. **This completes the backend.** Also add a section called "Backend API summary for frontend": every endpoint with its request and response JSON examples, which M09 and M10 use to write the TypeScript types.
