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

All application code lives in three files:

- **`main.py`** — FastAPI app with lifespan (DB pool setup/teardown), all route handlers, and business logic. Uses `text()` for raw SQL — no ORM mapping.
- **`models.py`** — Pydantic request and response models.
- **`utils.py`** — `make_url()` for pagination URL rebuilding; `CommaSeparatedInts` FastAPI dependency for multi-value int params.

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

Copy `.env.example` to `.env` for local development. Tests use `.env.test`.
