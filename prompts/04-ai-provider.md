# Prompt 04 — AI Provider Layer (Gemini via LangChain + Fake Provider)

**Depends on:** M01, M02 (storage/local_path for audio and images). **SPEC:** §2, §5, §12, §13, §15, §36, §41.

## Context intake
1. Follow `prompts/00-conventions.md` §A.
2. Read `docs/modules/M01-report.md`, `M02-report.md`, and `M03-report.md` (for context only; this module adds no endpoints). Open `app/core/config.py`, `app/core/errors.py`, `app/integrations/storage/*`, and `app/services/media_processing.py`.
3. Run the baseline and make sure it's green.

## Goal
One AI abstraction that the whole app uses. It's implemented by a Gemini provider built on LangChain and a deterministic fake for tests. Prompts live in versioned modules. **No LangGraph yet** (that's M05). This module delivers only the capabilities the graph will call.

## Build

### 1. AI schemas — `app/ai/schemas.py` (Pydantic, used for structured output)
- `TranscriptionResult`: `transcript: str`, `detected_language: Language` (en/bn/hi, the dominant one), `languages_present: list[Language]`, `is_code_mixed: bool`, `confidence: float | None`, `unclear_segments: list[str]`.
- SPEC §12 exactly: `Ingredient`, `RecipeStep`, `RecipeExtraction`. Add these extra fields:
  - on `RecipeExtraction`: `dish_name_en: str` (an English or transliterated name, used for the slug and SEO), `cuisine: str | None`, `category: str | None`, `description: str | None`, `servings: str | None`, `uncertainties: list[str]`.
  - on `Ingredient`: `is_quantity_explicit: bool`.
- Field descriptions must spell out SPEC §13: `null` when something wasn't stated, never invented.
- `ImageStepMatch`: `image_id: str`, `step_number: int | None`, `confidence: float` (0–1), `reason: str`, `description: str` (what's visible, used for alt text).
- Keep blog and SEO schemas out of this module. M07 adds them (`BlogDraft`, `SeoMetadata`) to this same file, following the same pattern.

### 2. Provider interface — `app/ai/provider.py`
```python
class AIProvider(Protocol):
    async def transcribe(self, audio: AudioInput, language_hint: Language) -> TranscriptionResult: ...
    async def extract_recipe(self, transcript: str, language: Language) -> RecipeExtraction: ...
    async def match_image_to_steps(self, image: ImageInput, steps: list[RecipeStep], context: RecipeContext) -> ImageStepMatch: ...
    async def generate_structured(self, prompt: PromptSpec, schema: type[T], variables: dict[str, Any]) -> T: ...  # generic hook used by M07
```
- `AudioInput` / `ImageInput` are small dataclasses: `path: Path`, `mime_type: str`. Providers read the file themselves. **Don't pass ORM objects or URLs.**
- `get_ai_provider(settings) -> AIProvider` picks the provider from `AI_PROVIDER` (`gemini` | `fake`, enum). It's the **only** constructor used by the app. Tests and dev-without-key use `fake`.
- Every provider error is translated into `AIProviderError(code, retryable: bool)`. Retryable means timeouts, 429, and 5xx. Not retryable means safety blocks, invalid output after repair, and auth/config problems.

### 3. Prompts — `app/ai/prompts/`
- `recipe_extraction.py`, `transcription.py`, `image_matching.py`. Don't create placeholder files for blog and SEO; M07 adds `blog_generation.py` and `seo_generation.py`.
- Each file exports a `PromptSpec(name, version, system, user_template)` (a frozen dataclass in `app/ai/prompts/base.py`), for example `RECIPE_EXTRACTION_V1`. Changing a prompt means bumping `version`. Log the prompt name and version on every call, never the content.
- The prompt content must enforce:
  - **Transcription:** a verbatim transcript that keeps the original script for Bengali and Hindi, doesn't translate, handles code-mixing (the SPEC §5 example), and marks unclear parts `[unclear]`.
  - **Extraction:** SPEC §13 accuracy rules, quoted literally. Understand code-mixed input. Write the output fields in the language the UI needs; decide this, document it, and default to the transcript's detected language plus an English `dish_name_en`. Normalize the ingredient name but keep the original term in `notes` when it's translated. Steps are ordered and atomic. Suggestions come only from the speaker's own tips, or are clearly labelled as general guidance.
  - **Image matching:** pick the single best step or `null`, calibrate confidence honestly, and never guess.

### 4. Gemini provider — `app/ai/gemini.py`
- Uses `langchain-google-genai` `ChatGoogleGenerativeAI`, with the model name from settings: `GEMINI_MODEL`, and optional `GEMINI_VISION_MODEL` and `GEMINI_TRANSCRIPTION_MODEL`. **Check the current model IDs in the official docs and don't hard-code a guess.**
- Structured output with `.with_structured_output(Schema)`. If validation fails, make **one** repair attempt that includes the validation error, then raise `AIProviderError`.
- Audio: multimodal message parts. When the file is bigger than the inline limit, use the Gemini Files API through the official `google-genai` SDK. That's allowed inside this file only, with a comment explaining why LangChain alone isn't enough. Run the M02 `normalize_audio_for_ai` first when the MIME type isn't supported.
- Vision: image parts with the recipe steps as text context.
- Timeouts, and retries with exponential backoff for retryable errors only (`tenacity` or the LangChain built-in). Record the call duration and token usage in structured logs, never the prompt text or transcript.
- A missing `GEMINI_API_KEY` raises `ConfigurationError("GEMINI_API_KEY is not set; set it or use AI_PROVIDER=fake")` **the first time it's used**, not at import.

### 5. Fake provider — `app/ai/fake.py`
- `FakeAIProvider` returns deterministic data: a code-mixed Bengali/English transcript for "Aloo Posto", plus a matching `RecipeExtraction` with 6 ingredients (one of them with `quantity=None` and the SPEC §13 note) and 4 steps.
- `match_image_to_steps` is deterministic by filename. For example, `step2_*.jpg` gives step 2 with confidence 0.9, and `random_*.jpg` gives `None` with 0.2. Document the rule.
- Configurable failures for tests: `FakeAIProvider(fail_on={"extract_recipe": AIProviderError(...)})`, plus call counters so tests can assert calls happened (or were skipped).
- It also works for `AI_PROVIDER=fake` in local dev, which lets the whole app run without a key.

### 6. Accuracy guard — `app/ai/validation.py`
A deterministic post-check run after extraction:
- Drop an ingredient only if its name, and the name in `notes`, is absent from the transcript. Log a warning and add an `uncertainties` entry; don't drop silently. Do **fuzzy/normalized** matching, and allow transliteration by matching against both the original and the English term.
- Null out any duration or temperature that doesn't appear in the transcript as a number, and add an uncertainty.

This is the code-level backstop for SPEC §13. Keep it conservative and well tested.

## Tests
**Unit**
- Schema tests: SPEC §12 fields are required and nullable as specified, and invalid confidence (>1) is rejected.
- Every `PromptSpec` has a name and a version, and the templates render with the expected variables and no missing keys.
- `get_ai_provider` picks fake or gemini. A missing key raises `ConfigurationError` on first call.
- `FakeAIProvider` is deterministic, and its failure injection works.
- Accuracy guard: an invented ingredient gets flagged, an invented "180°C" is nulled, a transliterated ingredient (`পেঁয়াজ` / onion) is kept, and a code-mixed transcript works.
- `GeminiProvider` with a **mocked LangChain chat model** (inject a fake `BaseChatModel` such as `GenericFakeChatModel`, or monkeypatch): the structured-output path; the repair path, where the first output is invalid and the second valid; retryable versus non-retryable error mapping; and the large-audio path chooses the Files API (mocked). Confirm the logs contain no transcript text or key.

**Integration — provider + storage + media (M02)**
- Store the ffmpeg-generated audio in `LocalStorage`, then `storage.local_path(key)`, then `AudioInput`, then `FakeAIProvider.transcribe`, then `extract_recipe`, then the accuracy guard. The result is a valid `RecipeExtraction`.
- The same flow with the extracted audio from the M02 mp4 fixture (scenario B).
- **Optional live smoke test**, marked `live_ai` and skipped unless `GEMINI_API_KEY` is set and `RUN_LIVE_AI=1`: transcribe the generated sine file (expect an empty or unclear transcript without crashing) and extract a recipe from a short text transcript. Say in the report whether this ran.

## Acceptance
Full regression. `AI_PROVIDER=fake` is the default in the test settings. `mypy app` is clean for `app/ai`.

## Handoff
Write `docs/modules/M04-report.md`. Contracts: the `AIProvider` protocol, every schema (with its fields), `get_ai_provider`, `AIProviderError` (with retryable semantics), `PromptSpec` plus the prompt names and versions, the FakeAIProvider behaviour table (filename to match rule, fixture recipe content), the accuracy guard API, and the settings added (`AI_PROVIDER`, `GEMINI_MODEL*`, timeouts, `RUN_LIVE_AI`). Update `PROGRESS.md`.
