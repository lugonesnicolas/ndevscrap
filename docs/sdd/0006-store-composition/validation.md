# Validación

## Resultado

Implementación completa y validada localmente en Windows el 2026-09-26 sobre
`17f69e5`, en la rama `feat/0006-store-composition`. La iniciativa se cierra
el 2026-09-27 tras comprobar CI verde en Ubuntu en el pull request #9
(`AC-012`), integrado en `main` como `433f234`.

## Evidencia

- Base: `952fc1d` sobre `main` `96594b0`; especificación aprobada en `17f69e5`.
- Decisiones del usuario del 2026-09-26 registradas en la especificación:
  sesión sólo vía variable, tope de 2 rps y reemplazo de campos de nivel
  superior en el manifest v2.
- Revisión de arquitectura independiente del borrador (2026-09-26):
  `ready-with-conditions`, con dos bloqueantes y catorce hallazgos a corregir.
  - Bloqueantes: `raise ... from None` conservaba `__context__` con el valor
    del header, y el harness de transporte propuesto no procesaba
    `Set-Cookie`.
  - A corregir: omisión del `5xx` agotado como transitorio, errores de
    construcción clasificados como permanentes, coherencia entre `outcome` y
    `published`, reglas de composición, entradas del índice no declaradas,
    llamada única a `write_normalized`, logging idempotente, parseo estricto y
    contacto, `TypeVar` del núcleo, dirección de imports, análisis de imports
    relativos, mutaciones detectables, semántica de `Retry-After` y `stats()`,
    y permisos en Windows.
  - Sugerencias adoptadas: `trust_env=False`, redirects públicos sólo al
    mismo origen HTTPS, URL base sin credenciales, riesgo de rotación de
    cookies, `session_configured` en la tienda, umbrales enteros y cierre de
    brechas en 0004.

  Todo se incorporó a la especificación, al plan y al ADR-0003.
- Segunda pasada de arquitectura (2026-09-26): `ready-with-conditions`, sin
  bloqueantes. Se corrigieron el redirect público verificado después de
  enviarlo (ahora se sigue a mano y se valida cada salto antes de enviarlo) y
  la mutación de la política de cookies oculta por el vaciado del jar (dos
  capas con pruebas propias). También se ajustaron la definición de
  `retries`, la barra final de la URL base, las reglas de nombres, el riesgo
  de certificados con `trust_env=False`, el contrato de `StoredComponent` y la
  interpolación de los mensajes de calidad.
- `TASK-001`, pruebas primero: con las pruebas nuevas y adaptadas sobre el
  código de `17f69e5`, nueve módulos de prueba no colectan porque la API nueva
  no existe (`test_config`, `test_extract_dia_session`, `test_observability`,
  `test_quality`, `test_runner`, `test_storage`, `test_stores`,
  `test_transport` y `test_vtex_connector`), diez pruebas de CLI fallan y
  nueve pasan (ClubDIA, sesión, paquete, validador y tienda desconocida).
- Revisión QA de seguridad independiente (2026-09-26): sin bloqueantes. Se
  corrigieron:
  - un redirect público `https://evil\@shop/` que `urlsplit` y `urllib3`
    interpretan distinto: el destino se valida ahora con el parser del envío y
    se rechazan credenciales, barra invertida y caracteres de control, también
    en la URL base;
  - registros de urllib3 que interpolan headers crudos: los loggers ajenos a
    `ndevscrap` se emiten con mensaje fijo;
  - un archivo llamado `.secrets` en la raíz aceptado como destino de la
    sesión;
  - la ventana en la que el script escribía el secreto en un archivo previo con
    permisos amplios: ahora escribe un temporal `O_EXCL` con `0600` y lo
    reemplaza;
  - un HAR con forma inesperada, que ahora es `TypeError`.

  Se documentaron en el README el riesgo de carpetas sincronizadas (OneDrive)
  y en ADR-0003 el invariante de declarar sensible todo componente con sesión.
- Revisión QA de contrato independiente (2026-09-26): `ready-with-fixes`, sin
  bloqueantes. Se corrigieron:
  - evidencia de que los valores HTTP llegan al transporte (`build_transport`
    con valores no default y CLI con variables válidas);
  - límites exactos de 5% y 30% con el primer valor por encima;
  - el hash de configuración, que ahora se calcula antes de escribir archivos
    y rechaza configuración pública no serializable;
  - el log `run_failed` con `run_id` cuando falla la publicación;
  - enteros ASCII estrictos, una única barra final en la URL base y `match` por
    regla en las pruebas de composición, con reglas separadas para crítico
    sensible y crítico sin raw.
- Pruebas de mutación locales, fuera del repositorio: una copia de `src/` con
  una mutación a la vez se antepone en `PYTHONPATH`; la copia sin mutar pasa
  las 232 pruebas y las 22 mutaciones hacen fallar al menos una prueba:
  - redirects con sesión, redirect público a otro origen y redirect con
    credenciales;
  - quitar la política de cookies, quitar el vaciado del jar y quitar
    `trust_env=False`;
  - reintentar errores de construcción, levantarlos dentro del `except` y
    esperar dentro del `except`;
  - quitar el tope de `Retry-After`;
  - desactivar la deduplicación y desplazar en uno cada umbral de calidad;
  - importar `ndevscrap.stores` desde el runner;
  - escribir raw o páginas rechazadas de un componente sensible y permitir un
    crítico sensible;
  - clasificar un `503` agotado como `failed`;
  - interpolar registros de loggers ajenos;
  - ignorar el timeout en `build_transport` o las variables HTTP en la CLI;
  - omitir el log cuando falla la publicación.
- Verificación final en Windows 11, Python 3.12.14 administrado por uv
  0.12.18, árbol sin versionar sobre `17f69e5`:
  - `uv sync --all-groups`: OK.
  - `uv run pytest -q -p no:cacheprovider --basetemp <scratchpad>`: 232 pruebas
    correctas.
  - `uv run ruff check --no-cache .`: OK.
  - `uv run ruff format --check --no-cache .`: OK, 76 archivos.
  - `python scripts/validate_repository.py`: OK.
  - `python scripts/validate_repository.py --self-test`: OK.
- CI Ubuntu del [pull request #9](https://github.com/lugonesnicolas/ndevscrap/pull/9),
  integrado el 2026-09-26T23:48:50Z como `433f234`: todos los checks en verde.
  [CI/Test](https://github.com/lugonesnicolas/ndevscrap/actions/runs/36280534327),
  [Quality/validate](https://github.com/lugonesnicolas/ndevscrap/actions/runs/36280534312),
  [Security/CodeQL y dependency review](https://github.com/lugonesnicolas/ndevscrap/actions/runs/36280534304).

## Criterios de aceptación

- `AC-001`: satisfecho. Todas las pruebas de 0005 pasan adaptadas. La
  comparación con `17f69e5` muestra que cada aserción eliminada tiene un
  reemplazo equivalente o más estricto: mensajes de calidad exactos,
  `stats()` en lugar de `retries`, centinelas `SENTINEL` en lugar de
  `"secret"`, ausencia de cupones en current y de request de token en lugar de
  `coupons is None`, y `zip-code` verificado en todas las páginas. Los datos de
  `connector_version` y `postal_code` pasan a sus equivalentes v2. Sin cambios
  en la CLI, los códigos, la línea JSON, el layout ni los nombres de current;
  el `503` agotado sigue reteniendo el staging.
- `AC-002`: satisfecho por `tests/test_storage.py`: componente `items`,
  `published_count` por componente, rechazo sin tocar el disco de un
  componente no declarado o incoherente con `outcome`, stream interrumpido sin
  archivo, `failed_transient` con opcional publicado y entradas del índice con
  `file` inseguro, colisionado o ausente descartadas.
- `AC-003`: satisfecho por `tests/test_stores.py`: análisis `ast` con imports
  relativos del núcleo y de `connectors/vtex.py`, subproceso en el que importar
  el runner no carga `stores` ni `connectors`, registro con `dia` y definición
  falsa de un componente que publica sólo `items.jsonl`.
- `AC-004`: satisfecho por la forma de la definición DIA, el fallo estructural
  de ClubDIA sin rutas `clubdia`, la ausencia de `raw/clubdia` tras una corrida
  exitosa y 19 reglas de composición con mensaje propio y sin directorio de
  salida.
- `AC-005`: satisfecho: `DiaConfig` no existe, `zip-code` sale de `RunContext`
  (código `4321`), la capacidad sigue `page_size × max_pages`, y se rechazan
  URLs base con `http`, credenciales, query, fragmento, path, `//` o barra
  invertida.
- `AC-006`: satisfecho por la fixture de dos particiones (20 descubiertos, 18
  publicados, 1 rechazado, 1 duplicado, primera aparición conservada), por el
  espía que ve cinco filas escritas antes de pedir la página 2 y por los
  límites 1/20 frente a 1/19 y 70 frente a 69 sobre 100, con los mensajes
  vigentes.
- `AC-007`: satisfecho por defaults, lectura de entorno y variable vacía; 19
  valores inválidos que nombran la variable sin repetir el valor; contacto
  inválido; CLI con código `1` sin directorio de salida; CLI con variables
  válidas que llegan como `HttpSettings(30, 0.5, 5, 60)`; y `build_transport`
  con timeout, reintentos, espaciado y tope aplicados.
- `AC-008`: satisfecho por `tests/test_transport.py` sobre `RequestsTransport`
  real con un adapter falso que procesa `Set-Cookie`, montado en `https://` y
  `http://`: (a) redirects con sesión, públicos al mismo origen y rechazados
  antes de enviar; (b) errores de construcción reales de `prepare` y el
  `UnicodeEncodeError` simulado, con `__cause__` y `__context__` nulos, más el
  agotamiento por red sin contexto y esperas sin excepción activa;
  (c) política de cookies, vaciado del jar, prueba de control y `.netrc`
  ignorado; (d) tope de `Retry-After`, último intento, `nan`, negativo, `inf`
  y fecha HTTP. Las mutaciones correspondientes mueren. En el runner, un `302`
  de ClubDIA produce `authentication_required`.
- `AC-009`: satisfecho por el manifest v2 escrito en `<fecha>/`, igual a
  `to_dict()`, sin campos de nivel superior retirados, con requests, códigos,
  reintentos, duración y `published` por componente, y por el hash que no
  cambia con otra ruta y contenido de sesión pero sí con `HttpSettings`.
- `AC-010`: satisfecho por las líneas JSON de una corrida con `run_id`,
  `store` y `component`, sin centinelas con una causa encadenada, por el
  evento `run_failed` cuando falla la publicación, por la allowlist, el
  `exc_type` sin traceback y el mensaje fijo de loggers ajenos, y por la CLI
  que registra una excepción inesperada sólo por tipo.
- `AC-011`: satisfecho: `session.py` no menciona ClubDIA, la extracción del HAR
  vive en `stores/dia_session.py`, el script propone `.secrets/` y rechaza
  `output/` y `.secrets` como archivo, `.gitignore` y `.dockerignore` ignoran
  `.secrets/`, y un `.secrets/dia-session.json` en el directorio de trabajo no
  se carga sin la variable.
- `AC-012`: satisfecho. ADR-0003 aceptado y enlazado; pytest, Ruff y validadores
  correctos en Windows. Los checks CI/Test, Quality/validate, Security/CodeQL y
  Security/Dependency review del pull request #9 concluyeron con `SUCCESS`
  antes de su integración en `main` como `433f234`.

## Desviaciones

- La mutación planificada "conservar la última aparición de un duplicado" no
  es aplicable en streaming sin volver a cargar el catálogo; se reemplazó por
  "desactivar la deduplicación" y por los desplazamientos de umbral.
- Por la QA de seguridad, el plan se actualizó después de la aprobación en
  `DES-012` (validación de redirects y URL base con el parser del envío) y
  `DES-015` (mensaje fijo para loggers ajenos). No cambian requisitos ni
  alcance.
- El componente no sensible (catálogo) registra `"<Tipo>: <mensaje>"` en el
  manifest y en el log, como en 0005, y la CLI interpola el mensaje de errores
  de configuración y almacenamiento. Esos textos provienen de mensajes fijos
  del transporte, de la configuración o de rutas locales y no contienen
  material de sesión.
- `connectors/vtex.py` importa `https_origin` de `transport.py` para validar la
  URL base con el mismo parser que el envío; es una dependencia plataforma →
  núcleo permitida por `DES-001`.
- Riesgos aceptados sin cambios: conservar la primera aparición de un
  duplicado, logs en JSON, `trust_env=False`, rotación de cookies de ClubDIA a
  verificar en `0008`, y los riesgos operativos de 0005.
