# Prompt 10 — Recipe Editor, Image Picker, Preview, Public Blog

**Depends on:** M06, M07, M08, M09. **SPEC:** §15–§23, §24, §25, §42, §43, §45, §46.

## Context intake
1. Follow `prompts/00-conventions.md` §A.
2. Read the reports for M06, M07, M08, and M09. Open `frontend/src/api/*`, `src/types/api.ts`, `src/hooks/*`, the M09 common components and test utilities, and the placeholder pages to be replaced. From the backend, check the live OpenAPI output for the blog, publish, step-image, hero, ingredient-image, and similar endpoints.
3. Run the backend and frontend baselines and make sure they're green.

## Goal
Finish the review → edit → preview → publish loop (SPEC §23, §46) and the public blog page. Also serve a **server-rendered public blog** so the blog works without JavaScript and is crawlable (SPEC §17, §20). An SPA alone can't meet that, so the small backend addition below is in scope. Record it as a decision.

## Build

### 1. API + types (extend M09's files; don't create a second client)
`getBlog`, `updateBlog`, `publishRecipe`, `unpublishRecipe`, `getPublicBlog(slug)`, `getSimilar(id)`, `updateRecipe` (PATCH with replace-list semantics), `assignStepImage`, `setHero`, `removeIngredientImage`, and `refreshIngredientImage`, plus types for `BlogOut`, `PublicBlogOut`, `BlogUpdate`, `SimilarRecipeOut`, `StepImageOut`, and `IngredientImageOut`. The mutations invalidate the correct TanStack Query keys, and all the query keys live in one `src/api/queryKeys.ts`.

### 2. Editor — `/recipes/:id/edit` `RecipeEditorPage`
- Loads the recipe and the blog. If the job isn't COMPLETED, it redirects to processing.
- `RecipeEditor` holds a **local draft state** (a single `useReducer`, with no global store, SPEC §47) with a dirty flag, a "leave page?" guard, and **Save Draft** (PATCH recipe + PATCH blog), **Preview**, and **Publish** buttons.
- An uncertainty banner lists `uncertainties` and highlights ingredients with `quantity == null`, so the user can see what the AI wasn't sure about (SPEC §13).
- `IngredientEditor`: an editable table (name, quantity, unit, notes) with add, remove, and move up/down controls. Every control has an accessible label.
- `StepEditor`: title, instruction, duration, and temperature per step, with add, remove, and reorder (renumbered on save). Shows the photos assigned to each step.
- `ImagePicker`: shows the unmatched photos plus the photos for each step, with the AI confidence and reason. Assigning a photo to a step or back to unmatched uses a `<select>` per photo (keyboard friendly; drag-and-drop is optional on top). It can set or clear the hero from the uploaded photos, and highlights a **suggested hero** (M06) that needs confirmation. Ingredient images show their attribution and licence, with "Remove" and "Find another" controls.
- Blog fields: title and meta description (with live character counters against 60/160), an OG title and description, keywords, the slug (read-only once published, with an explanation), and the content editor as a **Markdown textarea** plus a preview toggle. Don't use a WYSIWYG library (keep it simple). The content is sanitized by the backend.
- `SeoPreview`: a Google-style snippet (title, URL, description) plus an OG card preview.

### 3. Preview — `/recipes/:id/preview` `BlogPreview`
Renders `BlogOut.rendered_html` inside the article layout, with a clear "Draft preview — not published" banner and Back to editor / Publish buttons. It inserts the backend-sanitized HTML through **one** `SafeHtml` component that runs a second sanitization pass with `DOMPurify`, using the same allowlist as M07 (defence in depth, SPEC §43). No other component uses `dangerouslySetInnerHTML`, and a lint rule enforces this.

### 4. Public blog — `/blog/:slug` `BlogPage` (React)
- Uses `getPublicBlog`. Sets `<title>`, the meta description, OG/Twitter tags, the canonical link, and the JSON-LD `<script type="application/ld+json">` from the backend's pre-serialized JSON. Use React 19 document metadata or a tiny `useDocumentHead` hook; don't add a library for a few tags.
- Layout: the hero image with alt text, the article through `SafeHtml`, and `AudioPlayer`/`VideoPlayer` wrappers. They're thin semantic wrappers around native `<audio controls>`/`<video controls>` with a fallback download link, so they work without custom JS. Then a "You may also like" grid of `SimilarRecipeCard` components.
- Proper heading hierarchy (one `h1`), `lang` on the article (for Bengali and Hindi content), and lazy images.

### 5. Server-rendered public blog (backend, small)
- `app/web/public_blog.py`: `GET /blog/{slug}` (**outside** `/api/v1`) returns a full HTML document rendered with Jinja2. It includes the head (title, meta, OG, canonical, JSON-LD), the sanitized `rendered_html`, the similar section, and a minimal inline stylesheet. Only published recipes are served; anything else is a 404 page. This page is the canonical URL, and it works with JavaScript disabled (native `<audio>`/`<video>`).
- `GET /sitemap.xml` covers the published blogs, and `robots.txt` goes with it.
- Write the routing plan (implemented in M11) into the report. The reverse proxy sends `/blog/*`, `/sitemap.xml`, and `/robots.txt` to FastAPI, and everything else to the SPA. The React `BlogPage` stays for in-app navigation and dev.

### 6. Minor: a "My recipes" list on the home page when drafts exist (uses `GET /recipes`), linking to edit or processing. Keep it small.

## Tests
**Component (Vitest + RTL + MSW)**
- `IngredientEditor`/`StepEditor`: add, remove, and reorder. The payload sent on Save Draft has the correct replace-list shape and renumbered steps.
- `ImagePicker`: assigning a photo calls `assignStepImage` with the right args and the UI moves the photo. Unassigning makes it unmatched. The suggested hero needs an explicit confirm. The attribution text is rendered.
- `RecipeEditorPage`: shows the uncertainty banner. The dirty guard fires on navigation. Publish success navigates to `/blog/:slug`. A publish 422 lists the missing fields.
- `SeoPreview`: the counters and truncation warnings.
- `SafeHtml`: strips `<script>`, `onerror`, and `javascript:` even if the backend returned them (a malicious MSW fixture), and keeps `<audio><source>`.
- `BlogPage`: sets the title, meta, canonical, and JSON-LD script, and renders the similar cards and the audio/video only when present.
- axe checks with zero violations on the editor, preview, and blog pages. The editor can be completed using only the keyboard.

**Backend tests for §5**
- The SSR page for a published slug: 200, `text/html`, contains `<title>`, the canonical, `application/ld+json`, `<audio controls>`, and **no `<script>` except JSON-LD**. Unpublished gives 404. The sitemap lists only published blogs.

**Integration — full loop against the real backend (fake AI)**
- Extend the M09 integration suite (`INTEGRATION=1`): upload audio + 2 photos, then wait for COMPLETED, then `updateRecipe` (change a quantity), then `assignStepImage` (the unmatched photo to step 2), then `updateBlog` (edit the title), then `publishRecipe`, then `getPublicBlog(slug)`. The HTML reflects the edited quantity and the manual photo assignment, and the JSON-LD `recipeIngredient` has the edited quantity.
- `fetch(PUBLIC_BASE_URL + /blog/{slug})` (the SSR page) shows the same content.

## Acceptance
- Frontend lint, typecheck, tests, and build are all green. The backend regression is green. The integration loop passed (paste the output).
- A manual browser check in the built-in browser (describe it in the report, with screenshots if you can). Edit a recipe, preview it, publish it, and open `/blog/:slug` on both the SPA and the SSR endpoint. Load the SSR page **with JavaScript disabled** and confirm the audio plays.

## Handoff
Write `docs/modules/M10-report.md`. Contracts: the new API functions and query keys, the component inventory with props, the `SafeHtml` allowlist, the SSR routes (`/blog/{slug}`, `/sitemap.xml`, `/robots.txt`), the reverse-proxy routing requirements for M11, and any known UX gaps. Update `PROGRESS.md`.
