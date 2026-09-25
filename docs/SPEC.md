# SPEC — Production-Ready AI Recipe-to-Blog Web Application

> Source of truth for all module prompts in `prompts/`. Module prompts cite sections as `SPEC §N`.
> If a module prompt and this spec conflict, the module prompt wins **only** where it explicitly says so (it records the decision in its handoff report).

Build a production-ready, maintainable and simple-to-understand web application that converts a user's recipe recording into a complete SEO-friendly recipe blog.

The application must support: audio-first recipe input; optional video input; English, Bengali, Hindi; automatic transcription; recipe information extraction; ingredient extraction; cooking-step extraction; cooking suggestions/tips; real ingredient images; optional user cooking images matched to recipe steps; optional final dish image used as hero/thumbnail; audio embedding in the generated blog; video embedding in the generated blog; SEO-friendly blog generation; similar recipe/blog recommendations.

## §1 Technology Stack

**Backend:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.x, PostgreSQL, Alembic, Redis, Celery (or another simple production-ready background-job mechanism), LangChain, LangGraph, Gemini API as the primary AI model/tool, FFmpeg for audio/video processing, httpx for external APIs, pytest, Ruff, MyPy where practical. Do NOT use Django.

**Frontend:** React, TypeScript, Vite, React Router, TanStack Query, Axios or fetch, simple modern CSS architecture. Do NOT use Next.js unless there is a strong technical reason. The frontend should be simple and easy to understand.

## §2 AI / Agent Architecture

Use LangGraph to orchestrate the recipe-processing pipeline. Use LangChain for LLM interaction, structured output, prompts, tool integration, model abstraction. Use Gemini as the primary AI provider. Keep the AI provider behind a service abstraction so another provider can be added later without rewriting the application.

```text
AIProvider
    └── GeminiProvider
```

Do not scatter Gemini API calls throughout the application.

## §3 Main User Flow

```text
User (Audio | Optional Video | Optional Hero Image | Optional Cooking Images)
  → Upload API → Create Recipe Job → LangGraph Workflow:
      Detect language → Transcribe audio → Extract recipe → Normalize ingredients
      → Generate cooking steps → Generate cooking suggestions → Find real ingredient images
      → Analyze user cooking images → Match cooking images to steps → Generate SEO blog
      → Generate structured metadata → Find similar recipes
  → Save final Recipe → Frontend displays blog
```

## §4 Audio is Primary

- Scenario A — `audio.mp3` only: process the audio.
- Scenario B — `video.mp4` only: extract audio using FFmpeg and process the extracted audio.
- Scenario C — `audio.mp3` + `video.mp4`: use the supplied audio as the primary transcription source; keep the original video for embedding. Do NOT transcribe both.

## §5 Supported Languages

English, Bengali, Hindi. Allowed values: `auto`, `en`, `bn`, `hi`. `auto` must be supported. Must work with code-mixed speech (e.g. "First আমরা onionটা fry করবো..."). Store the detected language.

## §6 Upload Requirements

Required: audio OR video containing audio. Optional: prepared dish image; multiple cooking photos.

```text
Recipe Recording
Language [ Auto ▼ ]
Audio [ Choose audio ]  OR  Video [ Choose video ]
Prepared Dish Image [ Choose image ]
Cooking Photos [ Choose multiple images ]
[ Generate Recipe Blog ]
```

Validate file types, file sizes, empty uploads, unsupported media, corrupted files. Do not trust client-side validation alone; validate everything on the backend.

## §7 Media Storage

Storage abstraction: local filesystem (development), S3-compatible object storage (production). No hard-coded local filesystem assumptions in business logic.

```text
StorageService
    ├── LocalStorage
    └── S3Storage
```

Configurable through environment variables.

## §8 Recipe Database Model (minimum)

- **Recipe**: id, title, slug, language, status, transcript, dish_name, description, instructions, created_at, updated_at
- **Ingredient**: id, recipe_id, name, quantity, unit, notes, order
- **RecipeStep**: id, recipe_id, step_number, title, instruction, duration, temperature
- **CookingSuggestion**: id, recipe_id, suggestion, order
- **MediaAsset**: id, recipe_id, type, url, mime_type, metadata — types: audio, video, hero_image, cooking_image, ingredient_image
- **StepImage**: id, recipe_id, step_id, media_asset_id, confidence
- **IngredientImage**: id, recipe_id, ingredient_id, image_url, source_url, license, attribution
- **Blog**: id, recipe_id, title, slug, meta_title, meta_description, content_html, content_markdown, canonical_url, created_at, updated_at
- **Job**: id, recipe_id, status, current_step, progress, error, created_at, updated_at

## §9 Recipe Status

`UPLOADED, QUEUED, PROCESSING, TRANSCRIBING, EXTRACTING, FETCHING_IMAGES, MATCHING_IMAGES, GENERATING_BLOG, COMPLETED, FAILED`. Frontend polls job status (polling first; WebSockets later).

## §10 LangGraph Workflow

```text
START → validate_input → prepare_media → transcribe_audio → extract_recipe → normalize_recipe
→ fetch_ingredient_images → match_cooking_images → generate_blog → generate_seo_metadata
→ find_similar_recipes → save_result → END
```

Each node has one responsibility. No giant node.

## §11 LangGraph State

```python
class RecipeGraphState(TypedDict, total=False):
    recipe_id: UUID
    audio_url: str
    video_url: str | None
    transcript: str
    detected_language: str
    recipe_data: RecipeData
    ingredient_images: list[IngredientImageData]
    cooking_images: list[CookingImageData]
    matched_images: list[StepImageMatch]
    blog: BlogData
    similar_recipes: list[SimilarRecipe]
    error: str | None
```

Small and explicit. No ORM objects in state.

## §12 Structured Recipe Extraction

```python
class Ingredient(BaseModel):
    name: str
    quantity: str | None
    unit: str | None
    notes: str | None

class RecipeStep(BaseModel):
    step_number: int
    title: str
    instruction: str
    duration: str | None
    temperature: str | None

class RecipeExtraction(BaseModel):
    dish_name: str
    language: str
    ingredients: list[Ingredient]
    instructions: str
    steps: list[RecipeStep]
    suggestions: list[str]
```

Use structured output; do not parse arbitrary LLM text manually.

## §13 Accuracy Rules

The AI must NOT invent ingredients, quantities, cooking temperatures, cooking times, preparation techniques. Represent uncertainty (`quantity: null`, or `notes: "Quantity was not clearly mentioned in the recording."`). No hallucination to make the blog look complete.

## §14 Ingredient Images

Find real standard images — do NOT generate fake AI ingredient images. Sources: Wikimedia Commons, Unsplash API, Pexels API.

```text
ImageSearchProvider
    ├── WikimediaProvider
    ├── UnsplashProvider
    └── PexelsProvider
```

Per ingredient: image search → select relevant image → store URL → store source → store attribution/license when required. Do not download/re-host copyrighted images unless the license permits; prefer storing the source URL and displaying the remote image.

## §15 User Cooking Images

Use Gemini vision to determine which step each photo belongs to. Input: image + recipe steps + recipe context → best matching step + confidence. Example output:

```json
{ "image_id": "...", "step_number": 3, "confidence": 0.91, "reason": "The image shows onions being sautéed, matching step 3." }
```

Low confidence → do not force; mark `unmatched`; user can assign manually later.

## §16 Hero Image

If provided: blog thumbnail, OG image, article hero. If not: use a suitable recipe image only if licensing permits. Never silently generate an artificial dish image unless explicitly configured as an optional fallback.

## §17 Audio Embedding

If audio exists: `<audio controls><source src="..." type="audio/mpeg"></audio>` under a section like "🎧 Listen to the recipe". Blog must work without JavaScript.

## §18 Video Embedding

If video exists: `<video controls><source src="..." type="video/mp4"></video>` near the beginning. Not embedded if no video.

## §19 Blog Generation

Structure: Hero Image; Title; Short Introduction; Recipe Overview; Ingredients; Ingredient Images; How to Make [Dish Name]; Step 1..N (image if available); Audio; Video if available; Cooking Tips; Serving Suggestions; Storage / Reheating (ONLY if supported by the source or clearly marked as general guidance); FAQ; Similar Recipes. No unsupported facts.

## §20 SEO Requirements

Generate: SEO title, meta description, URL slug, primary keyword, secondary keywords, OG title, OG description, image alt text, Recipe schema (schema.org/Recipe, valid JSON-LD). Fields: @context, @type, name, image, description, recipeIngredient, recipeInstructions, recipeCuisine, recipeCategory, keywords — only if known. Do not fabricate nutrition, calories, prep time, cook time, servings unless available or derived by a documented deterministic calculation.

## §21 SEO Content Rules

No keyword stuffing; reads like a human-written article. Natural keywords ("[Dish] recipe", "how to make [Dish]", "easy [Dish]", "[Dish] ingredients") when appropriate, not repeated unnaturally.

## §22 Similar Recipes

"You may also like" + recipe cards after the blog. PostgreSQL-compatible simple matching on dish name, ingredient overlap, cuisine, category, keywords. No vector DB; design so embeddings can be added later.

## §23 Blog Editor

User reviews/edits: dish name, ingredients, quantities, steps, suggestions, blog title, meta description, blog content, image assignments. AI content is never auto-published. Actions: Save Draft, Preview, Publish.

## §24 Frontend Pages

`/` landing · `/create` upload · `/processing/:jobId` status (Uploading ✓ / Transcribing ✓ / Extracting recipe ✓ / Finding ingredient images ... / Matching cooking photos / Writing blog) · `/recipes/:id/edit` editor · `/recipes/:id/preview` preview · `/blog/:slug` public blog.

## §25 Frontend UX

Clean, modern, not over-engineered. Reusable components: UploadForm, MediaUploader, ProcessingStatus, RecipeEditor, IngredientEditor, StepEditor, ImagePicker, BlogPreview, AudioPlayer, VideoPlayer, SimilarRecipeCard, SeoPreview. TypeScript types written manually from backend schemas. API calls only inside `src/api/`.

## §26 API Structure (REST, `/api/v1/` from the start)

```text
POST   /api/v1/recipes
GET    /api/v1/recipes/{id}
PATCH  /api/v1/recipes/{id}
POST   /api/v1/recipes/{id}/process
GET    /api/v1/jobs/{id}
GET    /api/v1/recipes/{id}/blog
PATCH  /api/v1/recipes/{id}/blog
POST   /api/v1/recipes/{id}/publish
GET    /api/v1/blog/{slug}
GET    /api/v1/recipes/{id}/similar
```

## §27 FastAPI Architecture

```text
backend/
├── app/
│   ├── main.py
│   ├── api/v1/{recipes.py, jobs.py, blogs.py}
│   ├── core/{config.py, logging.py, security.py}
│   ├── db/{session.py, base.py}
│   ├── models/{recipe.py, media.py, blog.py, job.py}
│   ├── schemas/{recipe.py, blog.py, job.py}
│   ├── services/{recipe_service.py, media_service.py, storage_service.py, blog_service.py}
│   ├── ai/{provider.py, gemini.py, prompts/, workflows/{state.py, graph.py, nodes/}}
│   ├── integrations/{image_search/, storage/}
│   └── workers/tasks.py
├── migrations/
├── tests/
├── alembic.ini
├── pyproject.toml
└── Dockerfile
```

Keep modules small; no unnecessarily deep abstractions.

## §28 Frontend Architecture

```text
frontend/
├── src/
│   ├── api/{client.ts, recipes.ts, jobs.ts}
│   ├── components/{common/, recipe/, blog/}
│   ├── pages/{HomePage, CreateRecipePage, ProcessingPage, RecipeEditorPage, BlogPage}.tsx
│   ├── hooks/  types/  utils/
│   ├── App.tsx
│   └── main.tsx
├── package.json  tsconfig.json  vite.config.ts
```

## §29 Configuration

Backend env: `APP_ENV, DATABASE_URL, REDIS_URL, GEMINI_API_KEY, STORAGE_BACKEND=local, S3_BUCKET, S3_REGION, S3_ACCESS_KEY, S3_SECRET_KEY, IMAGE_PROVIDER=wikimedia, UNSPLASH_ACCESS_KEY, PEXELS_API_KEY`.
Frontend env: `VITE_API_BASE_URL=http://localhost:8000/api/v1`. Never expose secrets to React.

## §30 Security

CORS configuration; file type validation; file size limits; MIME validation; filename sanitization; path traversal protection; rate limiting strategy; API authentication architecture; secure media URLs where appropriate; environment-based secrets; no API keys in frontend; no sensitive info in logs. Never log `GEMINI_API_KEY`, user-uploaded private media URLs, raw auth tokens.

## §31 Error Handling

Consistent API errors:

```json
{ "error": { "code": "RECIPE_PROCESSING_FAILED", "message": "Unable to process the recipe audio." } }
```

No raw stack traces to users; detailed errors logged server-side.

## §32 Logging

Standard `logging`, structured where practical: recipe_id, job_id, workflow_node, duration, status, error. Avoid logging full transcripts in production.

## §33 Background Processing

Never run the AI pipeline inside the HTTP request. FastAPI → Create Job → Queue → Worker → LangGraph. API returns immediately `{ "recipe_id": "...", "job_id": "...", "status": "queued" }`. Celery + Redis; straightforward worker.

## §34 Idempotency

Workflow safe to retry. Retrying a failed FETCH_INGREDIENT_IMAGES must not duplicate ingredient records. Use DB uniqueness constraints where appropriate.

## §35 Testing

Unit: extraction schemas, media validation, slug generation, ingredient image service, blog generation service, image matching logic. API: POST /recipes, GET /recipes/{id}, GET /jobs/{id}, PATCH /recipes/{id}. Workflow: mock Gemini, verify audio → transcript → recipe → images → blog. Never call real Gemini in normal tests.

## §36 Mock AI Provider

`class FakeAIProvider` returning deterministic recipe data — fast and free tests.

## §37 Docker

`docker-compose.yml` with backend, worker, frontend, postgres, redis. Starts with `docker compose up --build`. Production-oriented Dockerfile; non-root users where practical.

## §38 Database Migrations

Alembic; never rely on `Base.metadata.create_all()` for production schema. Provide an initial migration.

## §39 API Documentation

OpenAPI docs work. Every endpoint: summary, description, response model, status codes.

## §40 Production Quality

Prefer simple code; abstraction only with real value; single responsibility; type safety (type hints, Pydantic, TypeScript); no magic strings (enums/constants); no duplicated logic (centralize config, AI provider, storage, API client, media validation); no giant files.

## §41 AI Prompt Management

No huge prompts inside Python functions. `ai/prompts/{recipe_extraction.py, blog_generation.py, image_matching.py, seo_generation.py}`; versionable and easy to modify.

## §42 Blog Image Placement

Generator emits semantic placeholders, not URLs: `<figure data-step-image="2"></figure>`, `<figure data-ingredient-image="onion"></figure>`. Rendering replaces them later.

## §43 Blog HTML Safety

Sanitize generated HTML before storing/publishing. Allow only: p, h1, h2, h3, ul, ol, li, strong, em, img, figure, figcaption, audio, video, a. Prevent script, iframe, `javascript:`, event handlers.

## §44 SEO URL

Clean stable slug like `/how-to-make-aloo-paratha/`; never `recipe?id=123`.

## §45 Accessibility

Semantic HTML, alt text, keyboard navigation, accessible buttons and forms, captions/transcripts where possible, proper heading hierarchy. Meaningful alt text for ingredient and cooking images.

## §46 Important Product Behavior

User always sees and edits the extracted recipe before publishing. AI is an assistant, not the final authority. Upload → AI processing → Draft recipe → User reviews → User edits → Preview → Publish.

## §47 Do Not Overbuild

No microservices, Kubernetes, Kafka, vector DB, complex agent-to-agent architecture, unnecessary event buses, complicated frontend state management, unnecessary design systems. Modular monolith: React → FastAPI → PostgreSQL → Redis + Worker → LangGraph → Gemini + external image APIs.

## §48 Deliverables

Backend source; frontend source; DB models; Alembic migrations; LangGraph workflow; Gemini integration; image-search integration; media processing; REST API; React UI; tests; Docker configuration; `.env.example`; README; API documentation; development setup instructions.

## §49 README Requirements

Architecture, prerequisites, environment variables, local development, Docker development, database setup, migrations, running backend/worker/frontend, running tests, running linting, API endpoints, AI workflow, media storage, production deployment. Mermaid diagrams where useful.

## §50 Implementation Order

1 Backend foundation · 2 Recipe APIs · 3 Media · 4 AI · 5 Images · 6 Blog · 7 Frontend · 8 Similar recipes · 9 Testing · 10 Docker + production hardening.

## §51 Coding Style

Understandable by a mid-level Python/React developer. Explicit code (`recipe = await recipe_service.get_recipe(recipe_id)`). Comments only where useful. Avoid unnecessary generic repositories, factories, excessive inheritance, over-engineered DI, global mutable state.

## §52 Final Requirement

Before finishing: run backend tests; frontend type check/build; linting; check imports; Docker config; migrations; API schemas; fix obvious errors; README matches implementation. Never claim something works unless implemented. Missing third-party credentials → clean adapter + `.env.example` + graceful, useful configuration error. Should feel like a real production MVP: simple architecture + clean code + reliable AI workflow + good UX + production fundamentals.
