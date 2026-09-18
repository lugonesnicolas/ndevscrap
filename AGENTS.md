# Repository Guidelines

## Project Structure & Module Organization

NDevScrap is a Python, API-first scraping project designed to run unchanged on
local machines and in Docker-based headless environments. The implementation is
being bootstrapped; follow this target layout as files are added:

- `src/ndevscrap/`: CLI, shared contracts, transport adapters, and scrapers.
- `tests/`: pytest tests and offline fixtures such as `tests/fixtures/site.json`.
- `output/`: generated JSON or JSONL results; keep it out of version control.
- `Dockerfile`: portable runtime image. Keep provider-specific deployment files
  separate from scraper logic.

Organize one scraper per module, for example
`src/ndevscrap/scrapers/catalog.py`. Prefer API or static HTML extraction with
`requests`; introduce `httpx` for asynchronous or advanced HTTP needs, and use
Playwright only where a real browser is necessary.

## Build, Test, and Development Commands

The planned toolchain uses `uv` and a `pyproject.toml`. Once introduced, run:

```bash
uv sync                              # Install locked dependencies
uv run ndewscrap run <scraper> --output output/result.jsonl
uv run pytest                        # Run the offline test suite
uv run ruff check .                  # Lint
uv run ruff format --check .         # Verify formatting
docker build -t ndevscrap .          # Build the headless image
```

Use the same CLI command in Docker; the runtime may change, but scraper
behavior and output contracts must not.

## Coding Style & Naming Conventions

Use Python with four-space indentation, type hints for public interfaces, and
small functions with explicit error handling. Use `snake_case` for modules,
functions, variables, and CLI options; use `PascalCase` for classes. Let Ruff
enforce formatting and linting rather than hand-formatting around its rules.

## Testing Guidelines

Use pytest. Name test files `test_<module>.py` and test functions
`test_<behavior>()`. Test parsing, normalization, error handling, exit codes,
and JSON/JSONL output with saved HTML or JSON fixtures. Do not make the test
suite depend on live sites; no coverage threshold has been set yet.

## Commits, Pull Requests, and Security

The current history uses Conventional Commit-style messages, e.g.
`docs: add project README`; follow `feat:`, `fix:`, `test:`, `refactor:`, or
`docs:` with an imperative summary. Keep commits focused. PRs should explain
the scraper or runtime change, list validation commands run, link the relevant
issue when available, and include sample sanitized output for user-visible
changes.

Store URLs, tokens, limits, and credentials in environment variables. Keep
`.env` private, update `.env.example` for new settings, respect site terms and
`robots.txt` where applicable, and implement timeouts, rate limits, bounded
retries, and useful logs.
