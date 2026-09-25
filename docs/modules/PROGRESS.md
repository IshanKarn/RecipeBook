# Build Progress

| Module | Status | Report | Tests (pass/skip/fail) | Key contracts |
|--------|--------|--------|------------------------|---------------|
| M01 Backend foundation | DONE | [M01-report.md](M01-report.md) | 44 / 0 / 0 | `Settings`/`get_settings`, `create_app`, `get_session`/`session_scope`, `AppError`+`ErrorCode`, all models & enums, migration `0001`, `GET /api/v1/health` |
| M02 Storage & media | TODO | – | – | – |
| M03 Recipe API | TODO | – | – | – |
| M04 AI provider | TODO | – | – | – |
| M05 Workflow & worker | TODO | – | – | – |
| M06 Images | TODO | – | – | – |
| M07 Blog & SEO | TODO | – | – | – |
| M08 Similar recipes | TODO | – | – | – |
| M09 Frontend foundation & upload | TODO | – | – | – |
| M10 Frontend editor & blog | TODO | – | – | – |
| M11 Docker, hardening, release | TODO | – | – | – |

## Environment notes
- Dev Postgres: `localhost:5434` (5432 and 5433 are used by other services on this machine). Redis: `localhost:6379`.
- FFmpeg is not installed yet; M02 needs it.
- Repository is not a git repo yet, so no module commits have been made.
