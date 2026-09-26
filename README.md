# NDevScrap

NDevScrap es la base para construir y operar scrapers Python para múltiples
tiendas y plataformas con contratos consistentes. El proyecto prioriza APIs y
HTML estático, reserva el navegador para los casos que realmente lo necesitan y
mantiene separadas la extracción, la ejecución y la persistencia.

El repositorio contiene la base Python, las validaciones y el primer conector
VTEX/DIA con CLI local y Docker. Su evolución continúa mediante el ciclo SDD
definido en este repositorio.

## Principios

- Un monolito modular es el punto de partida; los límites internos deben permitir
  separar componentes cuando el volumen lo justifique.
- Un conector implementa un contrato estable y reutiliza componentes mediante
  composición.
- Las variaciones se modelan como plataforma, configuración de tienda y overrides
  específicos, en ese orden.
- La estrategia de acceso es API, luego HTML estático y finalmente Playwright.
- Toda ejecución debe ser observable, reintentable e idempotente.
- Los datos conservan su origen y avanzan por capas raw, normalized y current.
- No se eluden controles de acceso ni medidas antiabuso.

La descripción normativa y los trade-offs están en la
[guía de arquitectura](docs/architecture.md). Las decisiones duraderas se
registran como [ADR](docs/adr/README.md).
El conocimiento reutilizable descubierto sobre APIs se mantiene en el
[catálogo de plataformas](docs/platforms/README.md).

## Cómo se trabaja

Todo scraper o cambio funcional comienza con una iniciativa SDD. Antes de
programar deben estar aprobados sus requisitos y su plan; al finalizar, la
evidencia se registra junto al cambio.

1. Leer la [guía de contribución](CONTRIBUTING.md).
2. Crear la iniciativa desde las [plantillas SDD](docs/sdd/README.md) y, cuando
   corresponda, iniciar o actualizar su ficha en el catálogo de plataformas.
3. Aprobar `spec.md` y `plan.md`.
4. Implementar las tareas manteniendo trazabilidad con los requisitos.
5. Ejecutar las validaciones y completar `validation.md`.
6. Abrir un pull request usando la plantilla del repositorio.

El paquete [0001-repository-foundation](docs/sdd/0001-repository-foundation/spec.md)
muestra el proceso completo aplicado a esta base documental.

## Estructura objetivo

```text
src/                 CLI, contratos compartidos y conectores
tests/               pruebas y fixtures HTML/JSON locales
docs/                arquitectura, ADR e iniciativas SDD
scripts/             herramientas de desarrollo sin lógica de scraping
output/              resultados locales no versionados
Dockerfile           imagen portable para ejecución headless
```

`src/` y `tests/` contienen el esqueleto y la iniciativa
[0004-dia-vtex-connector](docs/sdd/0004-dia-vtex-connector/spec.md) incorpora la
primera CLI y el conector VTEX/DIA.

## Ejecutar DIA Online

La integración pública usa VTEX Intelligent Search y requiere un código postal
para contextualizar disponibilidad y precios:

```bash
uv sync --all-groups
uv run ndevscrap run dia --postal-code 1806 --output output
```

El código postal piloto predeterminado es `1806`, por lo que también se puede
omitir `--postal-code`. La salida queda en `output/dia/1806/`:

```text
<fecha>/                     último intento aceptado del día: raw gzip,
                             normalized JSONL y manifest de la corrida
attempts/<fecha>/<run_id>/   intentos en cuarentena o fallidos y snapshots
                             aceptados que fueron reemplazados
current/                     products.jsonl, coupons.jsonl y un índice con
                             hash y origen de cada archivo publicado
.staging-<fecha>/            sólo tras un fallo transitorio, para reanudar
```

`current` sólo cambia con datos que superaron los controles de calidad. La
línea base de volumen se toma del catálogo publicado en `current`. En la salida
JSON final de la CLI, `snapshot` es `<fecha>/` si el catálogo fue aceptado o
`attempts/<fecha>/<run_id>/` en otro caso; los códigos de salida son `0`
(éxito), `2` (éxito parcial) y `1` (fallo).

ClubDIA forma parte de la corrida desde la primera versión. La sesión se entrega
en un archivo JSON local no versionado con las cookies funcionales VTEX y el
`order-form-id` efímero que requiere la pantalla de cupones:

```json
{
  "headers": {"order-form-id": "valor-secreto"},
  "cookies": {"VtexIdclientAutCookie_diaio": "valor-secreto"}
}
```

Para renovar manualmente la sesión, inicie sesión en DIA, abra la pantalla
ClubDIA, exporte un HAR autorizado y ejecute:

```bash
python scripts/extract_dia_session.py "captura-día.har"
```

El script conserva sólo el material funcional mínimo en
`.secrets/dia-session.json`, un directorio ignorado por Git y por Docker; en
POSIX el archivo se crea con permisos `0600` y en Windows rigen las ACL del
perfil. Dentro del repositorio sólo acepta rutas bajo `.secrets/`. Si el
repositorio vive en una carpeta sincronizada (OneDrive, Dropbox), `.secrets/`
también se sincroniza: en ese caso use `--output` con una ruta local fuera de
esa carpeta. Luego defina
`NDEVSCRAP_DIA_SESSION_FILE` según `.env.example`: la sesión se lee sólo desde
esa variable, nunca de una ubicación implícita. Si todavía la tiene en
`output/secrets/`, apunte la variable a esa ruta o muévala a `.secrets/`. Nunca
incluya la sesión en argumentos, logs o archivos versionados. Si falta o expira,
el catálogo público puede publicarse pero la CLI devuelve estado parcial y
conserva el último `current` válido de cupones.

El transporte HTTP se configura con `NDEVSCRAP_HTTP_TIMEOUT_SECONDS` (20 s por
defecto), `NDEVSCRAP_HTTP_REQUESTS_PER_SECOND` (1, máximo 2),
`NDEVSCRAP_HTTP_MAX_RETRIES` (3) y `NDEVSCRAP_HTTP_MAX_RETRY_AFTER_SECONDS`
(120). Un valor inválido termina con código `1` antes de escribir resultados.
El transporte no usa proxies, certificados ni credenciales `.netrc` del entorno
(`HTTPS_PROXY`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE`), por lo que una red con
inspección TLS no está soportada. Las requests con sesión nunca siguen
redirects y las cookies de respuesta no se guardan.

Los logs se emiten por stderr como JSON, una línea por evento, con `run_id`,
`store` y `component`; nunca incluyen headers, cookies, tokens ni tracebacks. La
línea JSON final de resultado sigue saliendo por stdout. El manifest de cada
corrida (`schema_version` 2) informa plataforma, tienda, ubicación, versión del
paquete y, por componente, conector, conteos, duplicados, requests, códigos
HTTP, reintentos, duración y si se publicó.

La misma CLI está disponible en Docker:

```bash
docker build -t ndevscrap .
docker run --rm -v ./output:/app/output ndevscrap run dia \
  --postal-code 1806 --output /app/output
```

Para incluir ClubDIA en Docker, monte el archivo de sesión como secreto de sólo
lectura y defina `NDEVSCRAP_DIA_SESSION_FILE` dentro del contenedor.

La programación diaria pertenece al host, por ejemplo Task Scheduler o cron.

## Preparar el entorno

Se usa [uv](https://docs.astral.sh/uv/) para gestionar Python 3.12 y las
dependencias:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Cuando el primer conector añada configuración se creará `.env` desde
`.env.example`. La futura CLI conservará la misma interfaz en local y en
contenedores; los adaptadores cloud vivirán fuera de los conectores.

## Validar este repositorio

La documentación y los paquetes SDD se validan sin instalar dependencias:

```bash
python scripts/validate_repository.py
python scripts/validate_repository.py --self-test
```

GitHub Actions ejecuta estas comprobaciones en cada push y pull request. El
workflow de CI ejecuta además `pytest` y Ruff sobre el proyecto Python.

## Operación responsable

Las credenciales y los resultados sensibles nunca se versionan. Cada iniciativa
de scraper debe evaluar términos del sitio, `robots.txt` cuando corresponda,
timeouts, límites de frecuencia, retención y tratamiento de datos antes de ser
aprobada.
