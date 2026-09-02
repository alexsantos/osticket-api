# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A third-party FastAPI wrapper that exposes osTicket's MySQL/MariaDB database as a modern REST API. Authentication uses API keys stored in osTicket's `ost_api_key` table, checked via the `X-API-Key` header.

## Commands

### Development

```bash
# Install dependencies
uv sync --all-extras --dev

# Run locally (requires .env)
python main.py
```

### Testing

```bash
# Start the test database (MariaDB via Docker)
docker-compose -f docker-compose.test.yml up -d

# Run tests with coverage
uv run pytest --cov=. --cov-report=html

# Run a single test file
uv run pytest tests/test_api.py

# Run a single test
uv run pytest tests/test_api.py::test_function_name

# Teardown test database
docker-compose -f docker-compose.test.yml down
```

### Docker

```bash
docker build -t osticket-api .
docker run -d -p 8080:8080 \
  -e DB_USER=... -e DB_PASSWORD=... -e DB_HOST=... -e DB_NAME=... \
  osticket-api
```

## Architecture

All application code lives in four files:

- **`main.py`** — FastAPI app with lifespan (DB pool setup/teardown), all route handlers, and business logic. Uses `text()` for raw SQL — no ORM mapping.
- **`models.py`** — Pydantic request and response models.
- **`utils.py`** — `make_url()` for pagination URL rebuilding; `CommaSeparatedInts` FastAPI dependency for multi-value int params.
- **`osticket_client.py`** — HTTP fallback client for fetching attachment bytes via osTicket's own `file.php` signed-download endpoint when a file has no rows in `ost_file_chunk` (e.g. `ost_file.bk` is a non-database storage backend like filesystem `'F'`). Handles staff login (session + CSRF token), HMAC-SHA1 URL signing, and the download itself. No-op (returns `None`, preserving `content: null`) when its `OSTICKET_*` env vars are unset.

  **Gotcha:** the signature's `Id=` field must be `ost_file.id` (the file's own id), never `ost_attachment.id` — conflating the two silently produces a `404 "Unknown or invalid file"` indistinguishable from a genuine auth/lookup failure. See `osticket_client.build_signature()`'s docstring and its dedicated regression test before touching this code.

### Request Flow

1. `X-API-Key` header → `verify_token()` dependency validates against `ost_api_key` table
2. Route handler acquires a SQLAlchemy connection from the pool
3. A `SET NAMES utf8mb4` event listener fires on every connection (required for international characters)
4. Raw SQL executed via `engine.connect()` + `text()`
5. Results serialized via Pydantic response models

### Custom Field Filtering

`GET /tickets` supports dynamic custom field filters as query params. The logic in `main.py` detects params that don't match standard filter names, then builds SQL using `JSON_UNQUOTE(JSON_EXTRACT(...))` to handle both plain and JSON-encoded form field values in osTicket's `ost_form_entry_values` table.

### Testing Strategy

- `tests/conftest.py` provides a session-scoped DB engine and function-scoped connections that truncate test data after each test.
- The test engine is injected into the FastAPI app via monkeypatching.
- `tests/schema/install-mysql.sql` initializes the MariaDB test schema.

## Environment Variables

| Variable | Required | Default |
|----------|----------|---------|
| `DB_USER` | Yes | — |
| `DB_PASSWORD` | Yes | — |
| `DB_HOST` | Yes | — |
| `DB_NAME` | Yes | — |
| `DB_PORT` | No | `3306` |
| `PORT` | No | `8080` |
| `MAX_UPLOAD_MB` | No | `10` |
| `ROOT_PATH` | No | `` (empty) |
| `OSTICKET_BASE_URL` | No | — (fallback disabled) |
| `OSTICKET_SECRET_SALT` | No | — (fallback disabled) |
| `OSTICKET_STAFF_USERNAME` | No | — (fallback disabled) |
| `OSTICKET_STAFF_PASSWORD` | No | — (fallback disabled) |

The four `OSTICKET_*` variables must all be set together to enable the `osticket_client.py` fetch fallback (see Architecture); if any is missing, attachments without DB-stored content simply return `content: null` as before.

Copy `.env.example` to `.env` for local development. Tests use `.env.test`.

## Versioning

The project version is declared in two places that must be bumped together: `pyproject.toml` (`version`) and `main.py` (`FastAPI(..., version=...)`, which drives the version shown in `/docs`). Whenever one is bumped, update the other in the same change.

## Branching Model

This project follows git-flow: `main` holds released code, `develop` is the integration branch, and `feature/*`, `release/*`, and `hotfix/*` branches are cut from and merged back per the usual git-flow rules. Hotfixes branch off `main`, get merged into both `main` and `develop`, and are deleted afterward. The repo has two remotes, `origin` (Bitbucket, primary) and `github` (mirror); keep both in sync when pushing `main`/`develop`.
