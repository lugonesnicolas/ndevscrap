# NDevScrap

Base para construir scrapers Python **API-first** que se ejecutan con la misma
lógica en local y en un contenedor Docker apto para entornos cloud/headless.
Cada scraper separa la extracción de datos de los detalles de ejecución,
configuración y almacenamiento.

## Principios y arquitectura

- Priorizar APIs y HTML estático: usar `requests` como cliente HTTP habitual.
- Usar `httpx` sólo cuando se necesiten flujos asíncronos o controles HTTP más
  avanzados.
- Usar Playwright únicamente cuando el sitio requiera un navegador; el scraper
  conserva su contrato aunque el navegador se ejecute en modo headless.
- Mantener la lógica de extracción independiente de los adaptadores de red,
  navegador y almacenamiento. Así, local y Docker sólo cambian la configuración
  del runtime, no el scraper.

La estructura objetivo es:

```text
src/       # CLI, contratos compartidos y scrapers
tests/     # Pruebas y fixtures HTML/JSON
output/    # Resultados JSON/JSONL generados (no versionar)
Dockerfile # Imagen portable para ejecución headless
```

## Inicio rápido

Se usa [uv](https://docs.astral.sh/uv/) para gestionar Python y las
dependencias. Cree `.env` desde `.env.example` cuando el primer scraper añada
configuración:

```bash
uv sync
cp .env.example .env
uv run ndewscrap run <scraper> --output output/result.jsonl
```

La CLI es la interfaz pública: selecciona un scraper, recibe su configuración y
escribe registros serializables en JSON o JSONL. Una ejecución correcta termina
con código `0`; errores de configuración, extracción o escritura deben terminar
con un código distinto de cero y un mensaje registrado.

## Ejecución en Docker

Docker debe reproducir el mismo comando de la CLI sin cambiar la lógica del
scraper. Cuando exista el `Dockerfile`, el flujo será:

```bash
docker build -t ndevscrap .
docker run --rm --env-file .env -v "${PWD}/output:/app/output" ndevscrap \
  run <scraper> --output /app/output/result.jsonl
```

El proveedor cloud puede ejecutar esta imagen de forma programada o bajo
demanda. Los adaptadores específicos del proveedor deben vivir fuera de los
scrapers.

## Configuración y operación responsable

Configure URLs, tokens, límites y demás valores por variables de entorno. Use
`.env` sólo en local, mantenga `.env.example` sin valores secretos y nunca suba
credenciales ni resultados sensibles al repositorio.

Antes de extraer datos, revise los términos del sitio y `robots.txt` cuando
corresponda. Cada scraper debe aplicar timeouts, rate limits, reintentos
acotados y logging útil; no debe intentar eludir controles de acceso ni medidas
antiabuso.

## Calidad y contribuciones

Las pruebas usarán `pytest` y fixtures locales de respuestas HTML/JSON, evitando
que la suite dependa de sitios externos. Antes de enviar cambios, ejecute:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Incluya pruebas para la transformación de datos, errores HTTP y formato de
salida. Mantenga los cambios pequeños, describa el scraper o adaptación añadida
en el commit y documente cualquier nueva variable de entorno en `.env.example`.
