# Plan de implementación

## Diseño

- `DES-001`: `current/manifest.json` pasa a ser un índice con
  `kind: "current-index"` e `index_version: "1"`, separado del esquema de
  `RunManifest`, e identifica `store` y `postal_code`. Cada componente presente
  en current registra `run_id`, `snapshot_id`, `published_at`, `status` del
  componente, `records`, `normalized` (igual a `records`, para lectores
  anteriores), `sha256`, `file` (nombre en current), `source` (ruta relativa
  durable del archivo de origen) y `provenance` (`run` o `legacy`). El bloque
  `last_attempt` resume `run_id`, `status`, `finished_at` y ruta relativa de su
  manifest.
- `DES-002`: la línea base se obtiene de `components.catalog.records` de un
  índice válido. Si el índice falta, no es JSON válido, no tiene
  `kind: "current-index"` o no tiene entrada `catalog`, se cuentan las filas de
  `current/products.jsonl`; sin archivo, la línea base es `None`. Al migrar un
  current heredado, los archivos presentes se registran con
  `provenance: "legacy"`, `run_id: null`, `source: null`, conteo y hash
  calculados.
- `DES-003`: el runner comunica el desenlace del catálogo con un tipo
  `CatalogOutcome` definido en `contracts.py`, que reemplaza al booleano
  `publish_catalog`:
  - `accepted`: primero se arma el nuevo current en un directorio temporal con
    las rutas finales. Luego el `<fecha>/` válido previo, si existe, se renombra
    a `attempts/<fecha>/<run_id-anterior>/` (el `run_id` se lee de su manifest;
    si no es legible o no produce un nombre seguro se usa
    `superseded-<finished_at UTC>`), el staging pasa a ser `<fecha>/` y por
    último se reemplaza current. Si falla el segundo renombrado, el directorio
    archivado vuelve a `<fecha>/`; si falla el reemplazo de current, `<fecha>/`
    vuelve a ser staging y el archivado vuelve a `<fecha>/`. En ambos casos se
    elimina el current temporal y el error se propaga como error de
    almacenamiento. Las entradas del índice cuyo `source` apuntaba al snapshot
    archivado, y la ruta del manifest de `last_attempt` si apuntaba allí, se
    reescriben a su nueva ruta.
  - `quarantined`: el staging completo se renombra a
    `attempts/<fecha>/<run_id>/`.
  - `failed`: fallo estructural o de configuración; igual que `quarantined`.
  - `failed_transient`: `TransportError` que no es `HttpStatusError`, o
    `HttpStatusError` con un código del conjunto reintentable del transporte
    (`429`, `500`, `502`, `503`, `504`) tras agotar reintentos. Otros `5xx` se
    tratan como `failed`. El staging se conserva y en
    `attempts/<fecha>/<run_id>/` se escribe el manifest y, si ClubDIA tuvo
    éxito, `normalized/coupons.jsonl`.
- `DES-004`: la publicación de ClubDIA en current es independiente del
  desenlace del catálogo. Si ClubDIA fue exitoso, su archivo se copia a current
  desde su ubicación durable (`<fecha>/` o `attempts/...`), nunca desde staging.
- `DES-005`: `prepare()` reutiliza `.staging-<fecha>` si existe, pero elimina
  todo salvo `raw/` y `checkpoint.json` (incluido `rejected/`) y los temporales
  `*.tmp` dentro de `raw/`, de modo que ninguna salida normalizada, página
  rechazada, escritura interrumpida o manifest de un intento previo llegue al
  nuevo snapshot. También elimina directorios `.current-*` huérfanos.
- `DES-006`: el runner confirma una página con `write_raw()` recién después de
  que `normalize()` termina sin error. Si el ítem trae `prefetched`, se usa esa
  respuesta y se sobrescribe el raw previo; si no, se intenta `read_raw()` y,
  en su defecto, `extract()`. `write_raw()` escribe a un temporal y usa
  `os.replace`; `read_raw()` trata `EOFError`, `gzip.BadGzipFile`,
  `zlib.error`, JSON inválido, campos faltantes o una clave guardada distinta
  de la pedida (dos claves pueden sanitizarse al mismo nombre) como raw
  ausente. Una página
  que falla al normalizar se guarda en `rejected/<componente>/<clave>.json.gz`
  del staging, que `read_raw()` nunca lee, y viaja con el staging a
  `attempts/` cuando el desenlace es `failed`.
- `DES-007`: el runner ejecuta cada componente dentro de su propio manejo de
  errores y ClubDIA se intenta aunque el catálogo falle. Ningún error de
  ClubDIA copia el texto de una excepción; se registran mensajes fijos:
  - sesión no configurada: indicación de `NDEVSCRAP_DIA_SESSION_FILE`;
  - sesión inválida o token ausente:
    `"<Tipo>: ClubDIA session unavailable or rejected"`
    (`authentication_required`);
  - `401` o `403`: `"ClubDIA session rejected with HTTP <código>"`
    (`authentication_required`);
  - otro estado HTTP: `"ClubDIA request failed with HTTP <código>"`;
  - errores esperados de transporte o datos: `"<Tipo>: ClubDIA request failed"`;
  - cualquier otra excepción: `"<Tipo>: unexpected ClubDIA failure"`, logueada
    sólo con el tipo, sin traceback ni `exc_info`.

  Los fallos del catálogo,
  que no transporta material de sesión, se loguean con tipo y mensaje en
  `ERROR` y con traceback sólo en `DEBUG`.
- `DES-008`: los reintentos se atribuyen por diferencia de `transport.retries`
  calculada en un bloque `finally` para cada componente.
- `DES-009`: `run_dia(config, *, transport=None, clock=None)` acepta un
  `Transport` y un reloj que devuelve el `datetime` consciente de zona;
  sin ellos construye `RequestsTransport` y usa `datetime.now(zone)`.
- `DES-010`: la CLI imprime como `snapshot` la ruta devuelta por `publish()`:
  `<fecha>/` para `accepted` o `attempts/<fecha>/<run_id>/` en otro caso. Un
  `OSError` de almacenamiento se informa como error de almacenamiento, no como
  error de configuración; el código de salida sigue siendo `1`.
- `DES-011`: `checkpoint.json` se mantiene como registro informativo. La fuente
  de verdad para reanudar es el raw confirmado mediante `read_raw()`.

## Contratos

```python
CatalogOutcome = Literal["accepted", "quarantined", "failed", "failed_transient"]


class SnapshotStore(Protocol):
    def publish(
        self,
        manifest: RunManifest,
        *,
        catalog_outcome: CatalogOutcome,
        publish_coupons: bool,
    ) -> Path: ...
```

- `publish_catalog` desaparece; el único caller y la única implementación se
  actualizan juntos. `previous_product_count()` conserva su firma y cambia su
  fuente según `DES-002`.
- `run_dia(config, *, transport=None, clock=None)`: parámetros opcionales
  compatibles.
- Layout de salida:

```text
output/<store>/<postal_code>/
  <fecha>/                     último intento válido del día
    raw/  normalized/  manifest.json  checkpoint.json
  attempts/<fecha>/<run_id>/   quarantined, failed o superseded (completo)
                               failed_transient (manifest y cupones)
  current/
    products.jsonl  coupons.jsonl
    manifest.json              índice kind=current-index
  .staging-<fecha>/            sólo tras failed_transient, para reanudar
```

- Los nombres de archivos de current, la CLI, la forma de su línea JSON y los
  códigos de salida no cambian. Quien leía el `RunManifest` desde
  `current/manifest.json` debe leerlo desde la ruta `source` o desde
  `<fecha>/manifest.json`; ningún código del repositorio lo lee hoy.

## Flujo de datos

1. La CLI crea `DiaConfig` y llama a `run_dia`.
2. `prepare()` crea o limpia el staging según `DES-005`.
3. Catálogo: discover; por ítem, `prefetched`, `read_raw` o `extract`;
   normalize; `write_raw` confirmado; calidad con la línea base de `DES-002`;
   `write_products`. Desenlace según `DES-003`.
4. ClubDIA: siempre se intenta con su propio manejo de errores; escribe cupones
   en staging sólo si tuvo éxito.
5. Se calcula el estado global con la regla vigente.
6. `publish()` aplica `DES-003` y `DES-004`: arma current con su índice de
   hashes y rutas durables en un directorio temporal, mueve el snapshot o el
   intento a su ubicación final y reemplaza current, con reversión si falla un
   paso.

## Fallos y recuperación

- `failed_transient`: staging retenido y limpiado al reanudar; current y
  `<fecha>/` válidos intactos.
- `quarantined` o `failed`: evidencia completa en `attempts/`; current y
  `<fecha>/` válidos intactos; la siguiente corrida parte de cero.
- Fallo de ClubDIA: `authentication_required` o `failed`; cupones de current
  intactos; catálogo sin cambios.
- En Windows, renombrar un directorio con archivos abiertos falla con
  `PermissionError`; el error se informa como error de almacenamiento, current
  y `<fecha>/` quedan como estaban antes de la corrida y el código es `1`.
- Un proceso terminado durante el reemplazo puede dejar `.current.backup`; la
  recuperación automática queda fuera de alcance.
- Riesgos operativos registrados, fuera de alcance: crecimiento de `attempts/`
  sin retención, ausencia de bloqueo entre corridas concurrentes del mismo día
  y descenso acumulado de la línea base en corridas aceptadas sucesivas.
- Rollback: revertir el commit. El índice conserva
  `components.catalog.normalized`, por lo que el código anterior sigue leyendo
  la línea base; un staging retenido sería publicado por el código anterior
  como snapshot, y los intentos en `attempts/` quedan como archivos inertes.

## Pruebas

- `tests/test_runner.py`, extremo a extremo con un transporte falso que enruta
  por URL, un reloj que avanza un minuto por llamada dentro del mismo día, la
  fixture de `tests/fixtures/clubdia` y páginas VTEX generadas con la forma de
  `tests/fixtures/vtex/product_page.json` para escalar el volumen:
  - éxito completo con hashes, fuentes del índice y `run_id` del manifest de
    origen (`AC-002`);
  - secuencia A/B/C escalada con hash de todo `<fecha>/` (`AC-001`, `AC-003`);
  - reintentos fallidos transitorio y estructural que no modifican `<fecha>/`
    (`AC-003`);
  - cero productos en cuarentena, sin `<fecha>/` y con cupones desde
    `attempts/`;
  - A aceptada con cupones y B aceptada con sesión vencida (`AC-002`,
    `AC-003`);
  - dos particiones, agotamiento de reintentos en la página 4 de la segunda y
    reanudación que vuelve a pedir el árbol y la página 1 de cada partición,
    más cupones del intento previo ausentes (`AC-004`);
  - página con estructura inesperada y gzip truncado (`AC-005`);
  - ClubDIA `401`, sesión ausente y excepción no prevista con contadores del
    catálogo iguales a la corrida base, y catálogo fallido con ClubDIA exitoso
    (`AC-006`);
  - reintentos por componente, incluido catálogo fallido (`AC-007`);
  - centinelas en salida y en `caplog.text` para respuestas vencidas, causas
    encadenadas que llegan o no al límite del componente, token ausente, sesión
    sin `order-form-id` y archivo de sesión malformado, con aserción del mensaje
    fijo registrado (`AC-008`).
- `tests/test_cli.py`: monkeypatch de `ndevscrap.cli.run_dia` para códigos
  `0`, `2` y `1`, campo `snapshot` y error de almacenamiento (`AC-009`).
- `tests/test_storage.py`: índice nuevo, índice corrupto, `RunManifest`
  heredado que describe un intento fallido, entrada `legacy` con origen nulo,
  índice sin entrada `catalog`, escritura atómica de raw, clave de raw
  colisionada, página rechazada fuera de `raw/`, limpieza del staging y de
  temporales al reanudar, snapshot previo sin `run_id` utilizable archivado como
  `superseded-*`, y restauración de `<fecha>/` y current cuando falla el
  renombrado del staging o el reemplazo de current (`AC-001`, `AC-002`,
  `AC-003`, `AC-005`).
- Pruebas existentes adaptadas a `catalog_outcome` sin debilitar sus
  aserciones.
- Revisión de seguridad independiente sobre `DES-007` y `AC-008` antes de
  integrar la rama.

## Despliegue

Sin migración: la primera corrida posterior lee el `current/manifest.json`
anterior mediante `DES-002` y lo reemplaza por el índice. Se actualiza la
descripción del layout de salida en `README.md` y se registran en
`0004-dia-vtex-connector/validation.md` los hallazgos posteriores, incluida la
nueva ubicación de los manifests de intento, con enlace a esta iniciativa. La
suite se ejecuta localmente en Windows y en CI Ubuntu. La evidencia de una
corrida real queda para `0008-release-v0-1-0`.
