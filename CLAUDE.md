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

## Architecture

- **`osticket_client.py`** — HTTP fallback client for fetching attachment bytes via osTicket's own `file.php` signed-download endpoint when a file has no rows in `ost_file_chunk` (e.g. `ost_file.bk` is a non-database storage backend like filesystem `'F'`). Handles staff login (session + CSRF token), HMAC-SHA1 URL signing, and the download itself. No-op (returns `None`, preserving `content: null`) when its `OSTICKET_*` env vars are unset.

  **Gotcha:** the signature's `Id=` field must be `ost_file.id` (the file's own id), never `ost_attachment.id` — conflating the two silently produces a `404 "Unknown or invalid file"` indistinguishable from a genuine auth/lookup failure. See `osticket_client.build_signature()`'s docstring and its dedicated regression test before touching this code.

## Environment Variables

The four `OSTICKET_*` variables must all be set together to enable the `osticket_client.py` fetch fallback (see Architecture); if any is missing, attachments without DB-stored content simply return `content: null` as before.

Copy `.env.example` to `.env` for local development. Tests use `.env.test`.

## Versioning

The project version is declared in two places that must be bumped together: `pyproject.toml` (`version`) and `main.py` (`FastAPI(..., version=...)`, which drives the version shown in `/docs`). Whenever one is bumped, update the other in the same change.

## Branching Model

This project follows git-flow: `main` holds released code, `develop` is the integration branch, and `feature/*`, `release/*`, and `hotfix/*` branches are cut from and merged back per the usual git-flow rules. Hotfixes branch off `main`, get merged into both `main` and `develop`, and are deleted afterward. The repo has two remotes, `origin` (Bitbucket, primary) and `github` (mirror); keep both in sync when pushing `main`/`develop`.
