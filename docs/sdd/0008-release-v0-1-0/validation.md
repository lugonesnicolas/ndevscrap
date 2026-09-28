# Validación

## Resultado

Validado el 2026-09-28 sin requests contra DIA. La release se registra tras integrar el pull request y confirmar CI en `main`.

## Evidencia

- `uv sync --all-groups`: OK.
- `uv run pytest`: 232 pruebas correctas (1 advertencia no bloqueante sobre la escritura de `.pytest_cache`).
- `uv run ruff check .`: OK.
- `uv run ruff format --check .`: OK, 85 archivos.
- `python scripts/validate_repository.py`: OK (enlaces y paquetes SDD).
- `python scripts/validate_repository.py --self-test`: OK.
- `docker build -t ndevscrap:0.1.0 .`: OK.
- Inventario de `git ls-files`: sin `.env`, cookies, sesiones, HARs, SQLite, logs ni `output/`; `.gitignore` ignora `.env`, `.secrets/`, `output/` y `*.har` (verificado con `git check-ignore`). El HAR local de la raíz no está versionado. Búsqueda de patrones de tokens/claves en archivos versionados fuera de `tests/` y `docs/`: sin coincidencias.
- Workflows `ci.yml`, `quality.yml`, `security.yml` y `auto-merge.yml` sin cambios; últimas ejecuciones en `main` y en la rama previa exitosas.

## Criterios de aceptación

- `AC-001`: satisfecho por el README en inglés.
- `AC-002`: satisfecho; badge de CI hacia `.github/workflows/ci.yml`.
- `AC-003`: satisfecho por el validador del repositorio.
- `AC-004`: satisfecho por las validaciones indicadas.
- `AC-005`: satisfecho por el inventario y las comprobaciones de `.gitignore`.
- `AC-006`: pendiente hasta publicar la release; se registra en el pull request.

## Desviaciones

- La iniciativa 0004 sigue `in-progress` por la evidencia pendiente de autorización operativa contra DIA; no se altera ni se ejecutó un smoke test real.
