# Prompt 09 — Frontend Foundation, Upload & Processing Pages

**Depends on:** M03, M05 (API contracts), M08 ("Backend API summary for frontend"). **SPEC:** §6, §24, §25, §28, §29, §45, §47.

## Context intake
1. Follow `prompts/00-conventions.md` §A.
2. Read `docs/modules/PROGRESS.md`, plus the M03, M05, and M08 reports. In particular, read the **"Backend API summary for frontend"** section and the upload validation limits (M02 `MEDIA_POLICY`).
3. Start the backend locally with `AI_PROVIDER=fake`, `AUTO_PROCESS_ON_UPLOAD=true`, and a Celery worker (or eager mode). Open `/docs` and check the real request and response shapes. **The TypeScript types must match the live OpenAPI output, not memory.**
4. Run the backend baseline and make sure it's green. The frontend doesn't exist yet.

## Goal
A simple, clean React + TypeScript app with routing, a typed API layer, the landing page, the upload page, and the live processing-status page. Editor and blog pages come in M10. Add routes for them now, rendering a minimal "Coming in M10" placeholder that M10 replaces.

## Build

### 1. Scaffold — `frontend/` (SPEC §28)
- Vite + React 18/19 + TypeScript in strict mode, React Router, and TanStack Query. **Plain `fetch`** wrapped in `src/api/client.ts` (no Axios, so there's one less dependency; write the choice down).
- Tooling: ESLint (typescript-eslint, react-hooks, jsx-a11y), Prettier, Vitest, `@testing-library/react`, `@testing-library/user-event`, `msw`, and `jsdom`. Scripts: `dev`, `build`, `preview`, `lint`, `typecheck` (`tsc --noEmit`), and `test`.
- CSS: plain CSS with custom properties (`src/styles/tokens.css`, `base.css`) and CSS Modules per component. Include light and dark mode through `prefers-color-scheme`. **No UI framework or design system** (SPEC §47).
- `.env.example` with `VITE_API_BASE_URL=http://localhost:8000/api/v1`, and **nothing secret**. Add a lint rule or test that fails if any `VITE_*` var name contains KEY/SECRET/TOKEN.
- Vite dev proxy for `/api` so cookies and CORS stay simple in development.

### 2. API layer — `src/api/`
- `client.ts`: a `request<T>(path, init)` helper for base URL handling and JSON. It parses the **error envelope** into a typed `ApiError { code: ErrorCode; message: string; status: number; details? }`, supports `AbortSignal`, and does **no** retries on 4xx.
- `recipes.ts`: `createRecipe(form: CreateRecipeInput, onProgress?)` uses `XMLHttpRequest`, because only XHR gives **upload progress** (write that down). Also `getRecipe` and `processRecipe`.
- `jobs.ts`: `getJob`.
- `src/types/api.ts`: types **written by hand** from the backend schemas (SPEC §25), covering `RecipeOut`, `JobOut`, `JobStepProgress`, `MediaAssetOut`, `ErrorCode`, `Language`, `RecipeStatus`, `JobStep`, and so on. Put a header comment that names the backend schema files they mirror.
- `src/hooks/`: `useRecipe(id)`, `useJob(id)` (TanStack Query `refetchInterval` of 2 s while the job isn't terminal, then it stops, and polling pauses while the tab is hidden), and `useCreateRecipe()`.

### 3. Shared validation — `src/utils/mediaRules.ts`
The client-side mirror of the M02 policy (extensions, MIME types, sizes, max photos), used **for UX only**. A comment says the backend is authoritative (SPEC §6). Keep the numbers in one place.

### 4. Components (SPEC §25)
- `components/common/`: `Button`, `Field` (label + hint + error, correctly linked with `aria-describedby`), `Alert`, `Spinner`, `ProgressBar` (with `role=progressbar` and aria values), and `Layout` (header/nav/main/footer landmarks plus a skip link).
- `components/recipe/MediaUploader`: a labelled file input + drag-and-drop area (keyboard accessible), with previews: image thumbnails, an audio/video file name + duration read from a `<audio>`/`<video>` metadata load, per-file validation errors, and remove buttons. It's used for audio, video, hero (single), and cooking photos (multiple, reorderable with up and down buttons, since the position matters).
- `components/recipe/UploadForm`: implements the SPEC §6 layout. It has the language select (Auto/English/বাংলা/हिन्दी) and the "Audio **or** Video" rule, with a clear message that explains Scenario C: "If you add both, the audio is used for transcription". The submit button is disabled with a reason until the form is valid. Show upload progress and render server errors from `ApiError` next to the relevant field. After a successful 202, navigate to `/processing/:jobId`.
- `components/recipe/ProcessingStatus`: renders `JobOut.steps` as the SPEC §24 checklist (✓ done, spinner for the current step, pending). It uses an `aria-live="polite"` region for step changes, plus a progress bar. On FAILED it shows the safe error message with a "Try again" button (calls `processRecipe`). On COMPLETED it shows a "Review your recipe" button that goes to `/recipes/:id/edit` (**no auto-publish**, SPEC §46).

### 5. Pages & routing — `src/App.tsx`
- `/` `HomePage`: a short value proposition, a 3-step "how it works", and a CTA to `/create`.
- `/create` `CreateRecipePage`.
- `/processing/:jobId` `ProcessingPage`.
- `/recipes/:id/edit`, `/recipes/:id/preview`, and `/blog/:slug` get minimal placeholders (M10 replaces them).
- A 404 page, and a top-level error boundary with a friendly message.

## Tests
**Unit / component (Vitest + RTL + MSW)**
- `client.ts`: parses the error envelope, handles a non-JSON 502 gracefully, and aborts.
- `mediaRules`: accepts and rejects by extension, MIME type, and size, and enforces the max photo count.
- `UploadForm`: submit is disabled with nothing selected. Audio only is valid, video only is valid, and both show the Scenario C note. An oversize file shows an error. A server 415 shows up next to the audio field. A successful submit navigates to the processing route (with a mocked XHR or an MSW handler).
- `useJob`: polls until COMPLETED and then stops (fake timers).
- `ProcessingStatus`: renders every step state. FAILED shows retry, and retry calls `processRecipe`. COMPLETED shows the review link.
- Accessibility: `vitest-axe` (or `jest-axe`) on `UploadForm` and `ProcessingStatus` with zero violations. The whole upload flow works with the keyboard only (user-event `tab`/`keyboard`).

**Integration — frontend ↔ real backend (M03 + M05, fake AI)**
- Add `frontend/tests/integration/` with a Vitest suite (marked with `INTEGRATION=1`, which is skipped otherwise) that uses the **real `src/api` functions** against a running backend (`VITE_API_BASE_URL`). It uploads a small generated audio file (commit a tiny, license-free WAV fixture of about 1 s of silence, generated with a script in the repo), polls `getJob` until it's COMPLETED, and asserts that `getRecipe` returns the ingredients. This proves the hand-written types match the real responses. Add a runtime shape check (a small `zod` schema **in tests only**, or a key-by-key assertion) against `RecipeOut`/`JobOut`.
- Write down in the report the exact commands used to start the backend, worker, and frontend for this test.

## Acceptance
- `npm run lint && npm run typecheck && npm test -- --run && npm run build` all pass.
- The integration suite has passed against the live backend (paste the output).
- Manual check (describe it in the report): with the dev server running, upload an audio file and watch the checklist advance to completed. Use the built-in browser to take a screenshot if you can, and reference it.
- The backend regression is still green.

## Handoff
Write `docs/modules/M09-report.md`. Contracts: the `src/api` function signatures, the `types/api.ts` inventory, the hook names and polling behaviour, the component props for `MediaUploader`/`UploadForm`/`ProcessingStatus`, CSS token names, the test utilities (`renderWithProviders`, MSW handlers file), the integration test command, and any backend mismatches found (along with the fix, which is allowed as a documented contract change). Update `PROGRESS.md`.
