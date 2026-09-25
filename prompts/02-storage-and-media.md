# Prompt 02 — Storage & Media Processing

**Depends on:** M01. **SPEC:** §4, §6, §7, §30, §40.
(SPEC phase order puts APIs before media. This module goes first so the upload API in M03 can be built on real validation and storage instead of throwaway code.)

## Context intake
1. Follow `prompts/00-conventions.md` §A.
2. Read `docs/modules/M01-report.md`. Open `app/core/config.py`, `app/core/errors.py`, `app/models/media.py`, `app/models/enums.py`, and the test fixtures it lists.
3. Run the baseline (conventions §E). Carry on only once it's green, or once you've fixed it and recorded the fix.

## Goal
A storage abstraction (local + S3-compatible), a strict media validation service, and FFmpeg-based probing and audio extraction. Everything is callable as plain Python. **This module adds no HTTP endpoints** (M03 adds them).

## Build

### 1. Storage — `app/integrations/storage/` + `app/services/storage_service.py`
- `StorageBackend` Protocol with these async methods:
  - `save(key: str, data: AsyncIterator[bytes] | bytes, content_type: str) -> StoredObject`
  - `open(key) -> AsyncIterator[bytes]`
  - `read_bytes(key) -> bytes`
  - `delete(key) -> None`
  - `exists(key) -> bool`
  - `local_path(key) -> AsyncContextManager[Path]`: gives FFmpeg and Gemini a real file. S3 downloads to a temp file and cleans it up afterwards.
  - `get_url(key, *, expires_in: int | None) -> str | None`: returns a presigned URL for S3 and `None` for local (M03 serves local media through an API route).
- `LocalStorage(root: Path)`: **path traversal protection**. It resolves the path and rejects any key that escapes `root`, is absolute, or contains `..` or a drive letter (Windows). It writes atomically (temp file, then rename) and streams in chunks.
- `S3Storage`: `aioboto3` (or boto3 inside `asyncio.to_thread` if simpler; say which in the report). It takes an endpoint URL setting so MinIO or R2 work, and raises `ConfigurationError` when the bucket or credentials are missing.
- `get_storage() -> StorageBackend` picks the backend from `STORAGE_BACKEND` (`local` | `s3`). Add a `StorageBackendType` enum, plus settings `LOCAL_STORAGE_ROOT` and `S3_ENDPOINT_URL`.
- Key scheme lives in one helper, `build_media_key(recipe_id, media_type, filename) -> str`, which produces `recipes/{recipe_id}/{media_type}/{uuid4}{ext}`. The user's filename is **never** used in the path. It's kept only as sanitized metadata.

### 2. Media validation — `app/services/media_validation.py`
- One policy table as data: `MEDIA_POLICY: dict[MediaType, MediaPolicy]` with allowed extensions, allowed MIME types, and max bytes (from Settings).
  - Audio: mp3, m4a, aac, wav, ogg, webm, flac.
  - Video: mp4, mov, webm, mkv.
  - Images: jpg, jpeg, png, webp, heic if feasible.
- `sanitize_filename(name) -> str`: strips paths and control characters, normalizes Unicode (Bengali and Devanagari names must survive readably or fall back safely), and limits the length.
- `sniff_mime(head: bytes) -> str | None` detects the MIME type from **magic bytes**. Use `filetype` or `python-magic`; pick the one that works on Windows without system libs, `filetype` is preferred. Never trust the client `Content-Type`. Reject when the extension, the sniffed MIME, and the declared type are inconsistent.
- `validate_upload(media_type, filename, stream) -> ValidatedUpload`. It streams while counting bytes, stops as soon as the size limit is exceeded (never buffer unlimited data), and raises `MediaValidationError` with an `EMPTY_UPLOAD`, `FILE_TOO_LARGE`, or `UNSUPPORTED_MEDIA` code. Images are decoded with Pillow (`verify()`) to catch corrupted files and read their dimensions. Strip EXIF GPS on re-encode only if that's cheap; otherwise say so in the report.
- `validate_submission(audio, video, hero, cooking_images)` enforces the SPEC §4/§6 rules: audio or video is required, at most `MAX_COOKING_IMAGES` photos, and one hero at most.

### 3. FFmpeg — `app/services/media_processing.py` (the only place that runs ffmpeg or ffprobe)
- `probe(path) -> MediaProbe` (duration, has_audio, has_video, codecs, container), using `ffprobe -v error -print_format json -show_streams -show_format` through `asyncio.create_subprocess_exec`. That means an argument list with **no shell** and a timeout.
- `ensure_decodable(path, media_type)`: raises `CORRUPTED_MEDIA` if probing fails, if an audio file has no audio stream, or if a video has no audio stream (SPEC §4 Scenario B needs audio).
- `extract_audio(video_path, out_path) -> Path`: mono 16 kHz, compressed so it's friendly for transcription. Choose opus/ogg or mp3 and document the choice.
- `normalize_audio_for_ai(path) -> Path` (optional transcode when the format isn't one Gemini accepts). Document the formats it accepts.
- `ffmpeg_available() -> bool`. Settings `FFMPEG_BINARY` / `FFPROBE_BINARY`, with a `ConfigurationError` if they're missing when needed.

### 4. `app/services/media_service.py`
- `async store_media(session, storage, recipe_id, media_type, validated_upload, position=None) -> MediaAsset` saves to storage and inserts a `MediaAsset` row (storage_key, mime, size, sanitized original filename, and probe/dimension metadata in `meta`).
- `async select_transcription_source(assets) -> TranscriptionSource` encodes SPEC §4 scenarios A, B, and C as a pure, easily testable function. It returns `{asset_id, needs_extraction: bool}`. With both audio and video present it returns the audio asset, and the video is never transcribed.

## Tests
**Unit**
- `LocalStorage`: save/read/delete round trip. Keys like `../x`, `/etc/passwd`, `C:\\x`, `a/../../b`, and URL-encoded traversal are rejected.
- `build_media_key` never contains the original filename.
- `sanitize_filename`: path stripping, control characters, Bengali and Hindi names, overlong names.
- `sniff_mime` and `validate_upload`: valid mp3/wav/mp4/jpg/png pass. Renamed files (a `.mp3` that's really a PNG) are rejected. Empty and oversize input fail fast: assert the stream wasn't fully consumed. A corrupted image fails.
- `validate_submission`: every valid and invalid combination (none, audio only, video only, both, too many photos).
- `select_transcription_source`: scenarios A, B, and C.
- `S3Storage` works against `moto` (save, read, presigned URL), and gives a `ConfigurationError` when the bucket is missing.

**Integration (`requires_ffmpeg`) — storage + ffmpeg + DB + models**
- Fixture: use ffmpeg to generate a 2 s sine-wave `mp3`, a 2 s `mp4` with an audio track, and an `mp4` **without** audio. Write them into a tmp dir so no binaries are committed.
- `probe` reports the correct streams. `ensure_decodable` rejects the silent video and a truncated or corrupted file.
- `extract_audio` on the mp4 produces a valid, probe-able audio file.
- `store_media` against real Postgres + `LocalStorage` in a tmp dir: the row exists, the file exists at the key, and `meta` has the duration.
- Works with S3 through moto: save, then `local_path` context, then `probe`, then the temp file is cleaned up.

## Acceptance
Full regression per conventions §E, including every M01 test. When ffmpeg is missing locally, the `requires_ffmpeg` tests **skip with a reason**, and the report must say they were skipped. Try to install ffmpeg (for example with `winget install ffmpeg` / `choco`) before accepting a skip.

## Handoff
Write `docs/modules/M02-report.md`. Contracts to list: the `StorageBackend` protocol, `get_storage`, `build_media_key`, `MEDIA_POLICY`, `validate_upload`, `validate_submission`, `ValidatedUpload`, `probe`, `extract_audio`, `ensure_decodable`, `store_media`, `select_transcription_source`, the new settings, and the reusable media fixtures (with their names). Update `PROGRESS.md`.
