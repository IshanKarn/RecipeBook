# Prompt 07 — Blog Generation, SEO, JSON-LD, Embeds, Publish Flow

**Depends on:** M03–M06. **SPEC:** §16–§21, §23, §26, §41–§44, §45, §46.

## Context intake
1. Follow `prompts/00-conventions.md` §A.
2. Read the reports for M03–M06. Open `app/models/blog.py`, `app/ai/schemas.py`, `app/ai/provider.py` (`generate_structured`), `app/ai/prompts/base.py`, the stub nodes `generate_blog.py` and `generate_seo_metadata.py`, `save_result`, `media_url_for`, the M06 alt-text sources, and `RecipeOut`.
3. Run the baseline and make sure it's green.

## Goal
Generate a human-quality draft recipe article from the extracted recipe, then store it sanitized, with semantic image placeholders. Produce the SEO metadata and valid schema.org/Recipe JSON-LD. Render the final HTML with the media embedded. Expose the blog, edit, preview, and publish endpoints. **Nothing gets published without an explicit user action.**

## Build

### 1. Schemas (append to `app/ai/schemas.py`, plus `app/schemas/blog.py` for the API)
- `BlogDraft` (LLM output):
  - `title`, `introduction`, `overview`
  - `sections: list[BlogSection]`, each with `kind` as an enum (`INGREDIENTS, STEPS, TIPS, SERVING, STORAGE, FAQ`), `heading`, and `body_markdown`
  - `faq: list[FaqItem]`
  - `storage_is_general_guidance: bool`
- `SeoMetadata`: `seo_title` (≤60 chars), `meta_description` (≤160), `slug_hint`, `primary_keyword`, `secondary_keywords` (≤6), `og_title`, `og_description`, and `hero_alt_text`. Validators enforce the lengths, and the text is truncated on word boundaries if it runs over.
- API: `BlogOut` (all fields + `rendered_html` + `json_ld` + `status` + `public_url`), `BlogUpdate` (editable fields: title, meta_title, meta_description, content_markdown **or** content_html, og_*, keywords, and slug with validation), and `PublishResponse`.

### 2. Prompts — `app/ai/prompts/blog_generation.py`, `seo_generation.py` (`PromptSpec` with versions)
- The blog prompt gets **only** the structured recipe (dish name, ingredients, steps, suggestions, uncertainties, language) plus the SPEC §13/§19/§21 rules. The rules it must follow:
  - No new facts; storage and serving tips only when the source supports them, otherwise labelled "General guidance".
  - FAQ answers must come from the recipe.
  - Natural keywords only, no stuffing.
  - Emit placeholders `<figure data-step-image="N"></figure>` and `<figure data-ingredient-image="normalized_name"></figure>` (SPEC §42), and never URLs.
- Article language: follow the recipe language, with an optional `BLOG_LANGUAGE` override. Document the choice.

### 3. Blog assembly — `app/services/blog_service.py` (deterministic code; the LLM writes prose only)
- `assemble_markdown(draft, recipe) -> str` builds the SPEC §19 order **in code**:
  - hero placeholder, title, intro, overview
  - an ingredient list rendered **from the DB data** (so quantities can never drift from the recipe) + an ingredient-image gallery placeholder
  - "How to Make {Dish}" + each step from the DB with its heading, instruction, and `data-step-image` placeholder
  - an audio placeholder `<figure data-media="audio">` + a video placeholder `<figure data-media="video">` (**placed near the start**, SPEC §18)
  - tips, serving, storage (only if present, with the guidance label), FAQ, and a similar-recipes placeholder
- `markdown_to_html` (markdown-it-py), then `sanitize_html`.
- `sanitize_html(html) -> str` uses **`nh3`**, following SPEC §43:
  - Allowed tags are exactly the SPEC list plus `source` (needed inside audio/video) and `h4`/`blockquote` only if you have a reason (write it down).
  - Allowed attributes per tag: `a[href,title,rel]`, `img[src,alt,width,height,loading]`, `figure[data-step-image,data-ingredient-image,data-media]`, `audio/video[controls,preload,poster]`, `source[src,type]`.
  - URL schemes: `https` and `http`, plus relative URLs for media. Force `rel="nofollow noopener"` on external links. `javascript:`, event handlers, `style`, `iframe`, and `script` are all removed.
  - Sanitize **on every write**: generation and user edits through PATCH.
- `render_blog_html(blog, recipe) -> str` resolves the placeholders at **read time** (so storage URLs are never baked in):
  - step image → `<figure><img src alt loading=lazy><figcaption>`
  - ingredient image → the image + an attribution `<figcaption>` with the licence link (**required**)
  - `data-media="audio"` → `<h2>🎧 Listen to the recipe</h2><audio controls preload="none"><source src type></audio>` + a `<details>` holding the transcript (accessibility and captions, SPEC §45)
  - video → `<video controls preload="metadata" poster=hero><source></video>`
  - unresolved placeholders are **removed**, never left empty
  - the output is sanitized again, and it works without JS
- `build_json_ld(recipe, blog, urls) -> dict`: schema.org/Recipe with `@context`, `@type`, `name`, `description`, `image` (the hero only; omitted if absent), `recipeIngredient` (from the DB strings), `recipeInstructions` (HowToStep with name and text, plus `image` when matched), `recipeCuisine`, `recipeCategory`, `keywords`, `inLanguage`, `datePublished` (only when published), and `author` if an owner name exists. **Include only known fields**: never `nutrition`, `prepTime`, `cookTime`, `totalTime`, or `recipeYield` unless the extraction explicitly carries them. `recipeYield` comes only from an explicitly stated `servings`. Document the deterministic rule, and emit the result through `json.dumps` with `</` escaped for safe embedding.

### 4. Slugs — `app/services/slug_service.py`
- `generate_slug(dish_name_en, hint) -> str`: `python-slugify` with Unicode-to-ASCII transliteration, `how-to-make-{dish}` style (SPEC §44), ≤80 chars. Bengali or Hindi-only names fall back to transliteration, and failing that to `recipe-{short-id}`.
- `ensure_unique_slug(session, base)` appends `-2`, `-3`, and so on. The DB unique constraint is the final guard (retry on IntegrityError).
- **Stable after publish**: once a blog has been published its slug can't change through PATCH (422). Keeping old slugs as redirects is left as a documented future item.

### 5. Nodes (replace the M05 stubs)
- `generate_blog`: `ai.generate_structured(BLOG_GENERATION_V1, BlogDraft, vars)`, then assemble, then sanitize. The result goes into `state["blog"]`.
- `generate_seo_metadata`: `ai.generate_structured(SEO_GENERATION_V1, SeoMetadata, vars)`, then validate and truncate, then produce the slug. The JSON-LD is built in code, not by the LLM.
- `save_result` upserts `blogs` (unique on recipe_id) with **status DRAFT**. On reprocess with force, the blog is regenerated **only** if it isn't published and hasn't been edited by the user (`blog.user_edited_at`, a new column via migration), unless `force_blog=true`.
- Extend `FakeAIProvider.generate_structured` to return a deterministic `BlogDraft` and `SeoMetadata`. One variant contains `<script>alert(1)</script>`, an `onerror=` attribute, and a `javascript:` link, which the sanitizer tests use.

### 6. Endpoints — `app/api/v1/blogs.py`
| Method | Path | Behaviour |
|---|---|---|
| GET | `/api/v1/recipes/{id}/blog` | Owner only. `BlogOut` with `rendered_html` (the preview). |
| PATCH | `/api/v1/recipes/{id}/blog` | Owner only. `BlogUpdate`, sanitized, sets `user_edited_at`. |
| POST | `/api/v1/recipes/{id}/publish` | Owner only. Requires recipe COMPLETED and a blog present. Validates that the title, meta description, ≥1 ingredient, and ≥1 step exist (otherwise 422 with the list of missing fields). Sets PUBLISHED, `published_at`, and `canonical_url = PUBLIC_BASE_URL + /blog/{slug}`. Idempotent. |
| POST | `/api/v1/recipes/{id}/unpublish` | Back to DRAFT (useful and small; document it). |
| GET | `/api/v1/blog/{slug}` | **Public**, no auth. Only PUBLISHED, otherwise 404. Returns a `PublicBlogOut` (rendered_html, SEO/OG fields, json_ld, hero url, and the media with public URLs). `Cache-Control: public, max-age=300`. |

- The M03 media route now allows public access to the assets of a **published** recipe. Private assets (such as an unused cooking photo) stay private. Decide and document whether "published" means the assets referenced in the rendered blog only (preferred) or all of them.

## Tests
**Unit**
- `sanitize_html`: script, iframe, `onerror`, `javascript:`/`data:` hrefs, and `style` are all stripped. The allowed tags and attributes survive, `<audio><source>` survives, and the placeholder `data-*` attributes survive.
- `assemble_markdown`: section order follows SPEC §19. Ingredient quantities come from the DB (mutate the DB value and it changes in the output). The storage section is absent when unsupported and labelled when it's general guidance.
- `render_blog_html`: every placeholder kind is resolved. Missing images and missing video are removed cleanly. The audio section includes the transcript `<details>`. The attribution caption is present.
- `build_json_ld`: valid against a JSON-schema subset or a structural checker. No prepTime/cookTime/nutrition when unknown. `recipeYield` only when servings are explicit. `</script>` gets escaped.
- Slug: Bengali and Hindi names, collisions (`-2`), length limits, and a slug that doesn't change after publish.
- SEO length truncation on word boundaries.

**Integration — full workflow → blog → publish → public (FakeAIProvider + respx)**
- Upload audio + video + hero + photos, and the workflow completes. `GET /recipes/{id}/blog` is DRAFT, and its `rendered_html` contains the hero `<img alt>`, the `<video>` placed before "How to Make", the `<audio>` section, step images for the matched steps, and an ingredient attribution. It contains **no** `<script>`.
- `GET /blog/{slug}` gives 404 before publish.
- `PATCH` the blog with a malicious `content_html`, then GET it: it's sanitized.
- `POST /publish`: `GET /blog/{slug}` gives 200, the JSON-LD parses and has `@type: Recipe`, and the canonical URL is correct. The media URLs in the public HTML are fetchable **anonymously**, and an unreferenced private asset is still 404 anonymously.
- `PATCH` the slug after publish gives 422. Reprocessing with force keeps the user-edited blog.
- Audio-only recipe: no `<video>` element appears.
- A publish validation failure lists the missing fields.

## Acceptance
Full regression plus the new migration round trip.

## Handoff
Write `docs/modules/M07-report.md`. Contracts: `BlogDraft`, `SeoMetadata`, `BlogOut`/`PublicBlogOut`/`BlogUpdate`, the placeholder grammar, `sanitize_html`'s allowlist (exact), `render_blog_html`, `build_json_ld`'s field rules, the slug rules, the endpoints, the public-media rule, the new migration, and a sample rendered HTML excerpt. Update `PROGRESS.md`.
