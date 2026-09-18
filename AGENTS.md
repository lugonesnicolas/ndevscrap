# Instrucciones para agentes

Estas reglas aplican a todo el repositorio.

## Antes de modificar

1. Lea `README.md`, `docs/architecture.md` y los ADR aceptados.
2. Lea `docs/sdd/README.md` y localice la iniciativa activa.
3. No implemente un scraper ni un cambio funcional si su `spec.md` y `plan.md`
   no están completos y la iniciativa no tiene estado `approved` o
   `in-progress`.
4. Si no existe una iniciativa adecuada, créela y deténgase en la aprobación
   antes de escribir código de producto.

## Estructura y límites

- `src/ndevscrap/`: CLI, contratos, adaptadores de transporte y conectores.
- `tests/`: pruebas pytest y fixtures HTML o JSON sanitizadas.
- `docs/`: arquitectura, ADR e iniciativas SDD.
- `scripts/`: herramientas de desarrollo sin lógica de scraping.
- `output/`: resultados generados; nunca se versionan.

Separe extracción, ejecución, configuración y almacenamiento. Prefiera API o
HTML estático; use Playwright únicamente cuando sea necesario y manténgalo detrás
del contrato del conector.

## Durante el trabajo

- Mantenga el alcance limitado a la iniciativa y sus tareas.
- Conserve trazabilidad entre requisitos, tareas, pruebas y validación.
- Actualice el SDD antes de introducir una desviación relevante.
- Use Python 3.12, type hints en interfaces públicas y funciones pequeñas con
  manejo explícito de errores.
- Use `snake_case` para módulos, funciones y variables, y `PascalCase` para
  clases. Deje el formato y lint a Ruff.
- Nombre pruebas como `test_<module>.py` y `test_<behavior>()`.
- Pruebe parsing, normalización, errores, idempotencia y contratos de salida con
  fixtures locales; la suite determinista no depende de sitios reales.
- No agregue secretos ni resultados sensibles. Documente nueva configuración en
  `.env.example`.
- No revierta cambios ajenos sin autorización.

## Comandos de validación

```bash
uv sync --all-groups
python scripts/validate_repository.py
python scripts/validate_repository.py --self-test
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Al finalizar

- Complete `validation.md` con evidencia reproducible.
- Cambie el estado a `done` sólo si todos los criterios están satisfechos.
- Use commits convencionales, enfocados y con resumen imperativo.
- En el pull request enlace el SDD, enumere validaciones y use muestras
  sanitizadas cuando cambie una salida visible.
- Si sincroniza o actualiza un fork, use operaciones seguras y nunca force push.
