---
id: 0006-store-composition
title: Composición de tiendas, publicación por componente y endurecimiento del transporte
status: in-progress
owner: maintainers
created: 2026-09-26
updated: 2026-09-26
approval: user-approved-2026-09-26
---

# Especificación

## Problema

Después de [0005-run-integrity](../0005-run-integrity/spec.md) los snapshots
son íntegros, pero el núcleo sigue acoplado a DIA y no cumple partes del
contrato de [0004-dia-vtex-connector](../0004-dia-vtex-connector/spec.md):

- `run_dia` está escrito para DIA: importa `VtexConnector`, `ClubDiaConnector`
  y `DiaConfig`, y decide nombres, mensajes y reglas de agregación de estado
  para esos dos componentes.
- `SnapshotStore` expone `write_products`, `write_coupons`,
  `previous_product_count` y `publish(..., catalog_outcome, publish_coupons)`,
  así que una tienda con otros componentes necesita cambiar el almacenamiento.
- `VtexConnector` recibe `DiaConfig`: la plataforma depende de la configuración
  de una tienda concreta.
- `session.py` mezcla el proveedor genérico de sesión con la extracción de un
  HAR de ClubDIA y sus mensajes nombran ClubDIA.
- La normalización acumula el catálogo completo en una lista y deduplica al
  final (`REQ-003` de 0004 exige no cargarlo entero en memoria).
- Timeout, ritmo y reintentos no se pueden configurar sin cambiar código
  (`REQ-008` de 0004).
- El manifiesto no informa plataforma, versión del paquete, versión de cada
  conector, requests, códigos HTTP, duplicados ni duración por componente, y no
  hay logs estructurados (`REQ-009` de 0004).
- La validación de 0005 derivó cuatro riesgos de seguridad del transporte:
  cookies y headers de sesión reenviados en un redirect a otro host, errores
  de construcción de la request reintentados con el valor del header en la
  excepción encadenada, cookie jar compartido entre componentes y
  `Retry-After` sin tope.
- El script de sesión escribe por defecto en `output/secrets/`, dentro del
  directorio de resultados que se monta en Docker.

## Objetivos

- Separar núcleo, plataforma y tienda: el núcleo ejecuta cualquier definición
  de tienda sin conocer DIA, VTEX ni ClubDIA.
- Mantener DIA como una definición de tienda que compone el catálogo VTEX
  (crítico) con ClubDIA (opcional).
- Normalizar en streaming con memoria acotada por página y por el conjunto de
  claves.
- Hacer configurable el transporte por entorno y cerrar los riesgos de
  seguridad derivados de 0005.
- Completar la observabilidad del contrato de 0004 con un manifiesto v2 y logs
  JSON por línea.
- Registrar la decisión transversal en ADR-0003.

## Alcance

Incluye `contracts.py`, `storage.py`, `runner.py`, `quality.py`, `models.py`,
`config.py`, `transport.py`, `session.py`, `cli.py`, el nuevo
`observability.py`, el nuevo paquete `src/ndevscrap/stores/` (registro,
definición DIA y extracción del HAR), `connectors/vtex.py` y
`connectors/clubdia.py` en lo necesario para las nuevas firmas,
`scripts/extract_dia_session.py`, `.gitignore`, `.dockerignore`,
`.env.example`, las pruebas correspondientes, el ADR-0003 y las secciones del
`README.md` que describen sesión, configuración y logs.

Excluye una segunda plataforma, Playwright, proxies, cloud, SQL, dashboard,
scheduler, retención de `attempts/`, bloqueo entre corridas concurrentes,
Docker non-root, la reescritura del README y de `docs/architecture.md`
(`0007-portfolio-documentation`), cambios en los endpoints o en la allowlist de
ClubDIA y cualquier corrida contra DIA o ClubDIA (la evidencia real queda para
`0008-release-v0-1-0`).

## Requisitos

- `REQ-001`: `SnapshotStore` debe operar por componente con
  `write_normalized(component, rows) -> int`, `published_count(component)` y
  `publish(manifest, *, outcome, published)`. El nombre del archivo de cada
  componente proviene de la definición de la tienda; para DIA siguen siendo
  `products.jsonl` y `coupons.jsonl`. El archivo normalizado de un componente
  sólo aparece en staging si su stream termina sin error. `publish` valida que
  lo publicado sea coherente con el desenlace del componente crítico antes de
  tocar el disco. Current sólo conserva una entrada del índice no declarada si
  su archivo tiene un nombre seguro y existe. Se conserva toda la
  semántica de 0005: línea base desde current, índice con procedencia,
  `attempts/<fecha>/<run_id>/`, reanudación sólo tras fallo transitorio y
  aislamiento de componentes.
- `REQ-002`: un runner genérico
  `run_store(definition, run_settings, http_settings, *, transport=None,
  clock=None)` debe ejecutar cualquier definición registrada en
  `src/ndevscrap/stores/`. Los módulos del núcleo no importan
  `ndevscrap.stores` ni ningún módulo de `ndevscrap.connectors`. La CLI obtiene
  las tiendas válidas del registro.
- `REQ-003`: una definición de tienda declara sus componentes con nombre,
  etiqueta, archivo de salida, conector, `critical`, `persist_raw`,
  `sensitive` y, opcionalmente, validador, clave de deduplicación y política de
  calidad. La composición se valida antes de crear archivos:
  - identificadores y nombres de archivo seguros y únicos, estos últimos sin
    distinguir mayúsculas;
  - exactamente un componente crítico, con conector, que persiste raw y no es
    `sensitive`;
  - un componente `sensitive` no persiste raw;
  - sólo el crítico tiene política de calidad;
  - la zona horaria es válida.

  Un componente con `persist_raw=False` nunca escribe raw ni páginas
  rechazadas. DIA compone el catálogo VTEX (crítico, `persist_raw=True`) con
  ClubDIA (opcional, `persist_raw=False`, `sensitive=True`).
- `REQ-004`: `VtexConnector` debe recibir `VtexSettings` (URL base, locale,
  moneda, canal de venta, tamaño de página y máximo de páginas por partición)
  y tomar el código postal de `RunContext`, sin depender de configuración de
  DIA. La URL base es HTTPS, sin credenciales, query, fragmento ni path más
  allá de una barra final. Los
  hallazgos de plataforma siguen en la
  [ficha de VTEX](../../platforms/vtex/README.md).
- `REQ-005`: la normalización debe procesar cada página y escribir sus filas
  antes de pedir la siguiente, deduplicar con un conjunto de claves
  (`sku_id`, `seller_id`) conservando la primera aparición y evaluar la calidad
  sobre contadores. Los umbrales siguen siendo cero válidos, más de 5% de
  inválidos y caída mayor a 30%, con los mismos mensajes. Para cada componente
  completado se cumple `discovered = normalized + rejected + duplicates`.
- `REQ-006`: el transporte debe configurarse con
  `NDEVSCRAP_HTTP_TIMEOUT_SECONDS` (default 20, rango (0, 300]),
  `NDEVSCRAP_HTTP_REQUESTS_PER_SECOND` (default 1, rango (0, 2]),
  `NDEVSCRAP_HTTP_MAX_RETRIES` (default 3, rango [0, 10]) y
  `NDEVSCRAP_HTTP_MAX_RETRY_AFTER_SECONDS` (default 120, rango (0, 3600]). Una
  variable vacía equivale a no definida. Un valor no numérico, no finito, no
  entero en `MAX_RETRIES` o fuera de rango es un error de configuración
  (código `1`) que se detecta antes de crear archivos, con un mensaje que no
  repite el valor. `NDEVSCRAP_CONTACT` debe ser ASCII imprimible de hasta 200
  caracteres. Las variables se documentan en `.env.example`.
- `REQ-007`: `RequestsTransport` debe:
  - (a) no seguir redirects en una request que lleve cookies o headers propios;
    el `3xx` se informa como `HttpStatusError` y, en un componente `sensitive`,
    como `authentication_required`. Una request pública sólo sigue redirects
    al mismo origen HTTPS, validados antes de enviar cada salto;
  - (b) no reintentar errores de construcción de la request (`InvalidHeader`,
    `InvalidURL`, `MissingSchema`, `InvalidSchema` y errores de codificación
    de headers) y levantar un error permanente con mensaje fijo. Ni ese error
    ni el de agotamiento de reintentos conservan causa o contexto. El backoff
    se espera fuera de todo bloque `except`;
  - (c) no persistir cookies de respuesta, de modo que ninguna cookie de un
    componente llegue a otro, y no agregar credenciales ni proxies del
    entorno;
  - (d) no esperar un `Retry-After` mayor que el tope configurado y levantar en
    su lugar un `TransportError` transitorio; un valor no finito o negativo se
    ignora.
- `REQ-008`: el transporte debe exponer `stats()` con requests enviadas,
  reintentos y conteo por código HTTP. `RunManifest` pasa a `schema_version`
  `"2"` con `platform`, `store`, `location.postal_code`, `package_version` y
  `configuration_hash`, sin `connector_version` ni `postal_code` de nivel
  superior; cada componente informa `connector_id`, `connector_version`,
  `status`, `discovered`, `normalized`, `rejected`, `duplicates`, `retries`,
  `requests`, `http_status_counts`, `duration_seconds`, `published` y `errors`
  redactados, atribuidos por diferencia de `stats()`. El hash de configuración
  cubre la configuración pública efectiva y registra sesión y contacto sólo
  como booleanos.
- `REQ-009`: la CLI debe emitir por stderr logs JSON de una línea por evento
  (`run_started`, `component_started`, `component_finished`, `run_finished` y
  errores) con `run_id`, `store` y, cuando aplique, `component`. Los logs
  serializan sólo campos permitidos y el tipo de una excepción, nunca headers,
  cookies, tokens ni tracebacks. La línea JSON final por stdout no cambia.
- `REQ-010`: la extracción del HAR y sus constantes de ClubDIA deben vivir en
  un módulo de la tienda DIA; `session.py` queda genérico y con mensajes
  neutros. El script escribe por defecto en `.secrets/dia-session.json` y sólo
  acepta rutas bajo `.secrets/` o fuera del repositorio. `.secrets/` se ignora
  en Git y en Docker. El runtime lee la sesión sólo desde
  `NDEVSCRAP_DIA_SESSION_FILE`, nunca de forma implícita.
- `REQ-011`: la decisión sobre definiciones de tienda y publicación por
  componente debe registrarse como ADR-0003 aceptado, enlazado desde el índice
  de ADR y desde el plan.
- `REQ-012`: no cambian la interfaz
  `ndevscrap run dia --postal-code <CP> --output <dir>`, su default `1806`, los
  códigos de salida `0`, `2` y `1`, la forma de la línea JSON final, el layout
  de salida, el índice de current (`index_version` `"1"`), los nombres de
  archivo de current ni los umbrales de calidad.

## Restricciones

- Sigue ADR-0001, ADR-0002 y el contrato de 0004 y 0005. ADR-0003 formaliza la
  capa de definición de tienda y la publicación por componente.
- Decisiones del usuario (2026-09-26): la sesión se lee sólo vía variable de
  entorno; el ritmo máximo configurable es 2 rps; el manifest v2 reemplaza
  `connector_version` y `postal_code` de nivel superior.
- La suite permanece determinista y sin red: el transporte, el reloj y el
  adapter HTTP se inyectan. Las pruebas de 0005 en `tests/test_runner.py`,
  `tests/test_storage.py` y `tests/test_cli.py` se adaptan a las nuevas firmas
  sin eliminar ni debilitar aserciones.
- La suite debe pasar en Windows, plataforma operativa local, y en CI Ubuntu.
- Sin nuevas dependencias de ejecución.
- La revisión de arquitectura del borrador (2026-09-26) quedó en
  `ready-with-conditions`; sus condiciones están incorporadas a este documento
  y al plan.

## Criterios de aceptación

- `AC-001`: todas las pruebas de 0005 pasan adaptadas, y la revisión del diff
  de pruebas confirma que cada aserción previa se conserva o se endurece.
  Sólo los datos de `connector_version` y `postal_code` de nivel superior
  pasan a sus equivalentes v2. La CLI, los códigos de salida, la línea JSON,
  el layout y los nombres de current no cambian. Un `503` agotado en el
  catálogo sigue reteniendo el staging. Vinculado con `REQ-012` y `REQ-001`.
- `AC-002`: `FileSnapshotStore` publica el archivo declarado por una definición
  ajena a DIA y `published_count` responde por componente. `publish` rechaza,
  sin tocar el disco, un componente no declarado o un crítico publicado sin
  desenlace `accepted`. Una excepción durante `write_normalized` no deja
  archivo normalizado en staging, y una entrada del índice con un `file`
  inseguro se descarta. Vinculado con `REQ-001`.
- `AC-003`: un análisis de imports, incluidos los relativos, no encuentra
  `ndevscrap.stores` ni `ndevscrap.connectors` en los módulos del núcleo, ni
  `ndevscrap.stores` o `connectors.clubdia` en `connectors/vtex.py`; importar el
  runner no carga `ndevscrap.stores`; el registro expone `dia`; una
  definición falsa de un solo componente corre con `run_store`, publica sólo su
  archivo y termina en `success`. Vinculado con `REQ-002`.
- `AC-004`: la definición DIA declara catálogo crítico con raw y ClubDIA
  opcional, sensible y sin raw, y un fallo estructural de ClubDIA no deja nada
  bajo `raw/clubdia` ni `rejected/clubdia`. Cada regla de composición de
  `REQ-003` violada produce `ValueError` antes de crear el directorio de
  salida. Vinculado con `REQ-003`.
- `AC-005`: `VtexConnector` se construye con `VtexSettings`, `DiaConfig` deja
  de existir, el parámetro `zip-code` de cada página es el código postal de
  `RunContext` y una URL base con credenciales, query, fragmento o path se
  rechaza. Vinculado con `REQ-004`.
- `AC-006`: una fixture de dos particiones con dos páginas cada una, un
  duplicado entre particiones y una fila inválida produce los contadores
  esperados, conserva la primera aparición del duplicado y escribe las filas de
  una página antes de pedir la siguiente; los límites de 5% y 30% exactos
  aprueban y el primer valor por encima falla, con los mensajes vigentes.
  Vinculado con `REQ-005`.
- `AC-007`: sin variables se usan 20 s, 1 rps, 3 reintentos y 120 s; valores
  válidos llegan al transporte y cambian el hash; una variable vacía usa el
  default; valores no numéricos, no finitos, no enteros donde corresponde,
  cero, negativos o por encima del rango, y un contacto inválido, hacen que la
  CLI devuelva `1` con `configuration error`, sin el valor en el log y sin
  crear el directorio de salida. Vinculado con `REQ-006`.
- `AC-008`: pruebas sobre `RequestsTransport` real con un adapter falso que
  procesa `Set-Cookie` como una respuesta real, montado en `https://` y
  `http://`, sin red, demuestran:
  - (a) una sola request y ninguna cookie enviada al host del `Location`
    cuando la request lleva sesión; un redirect público al mismo origen se
    sigue y uno a otro origen o a `http` se rechaza sin reintento y sin que el
    adapter reciba ninguna request hacia ese destino;
  - (b) para cada error de construcción, un solo intento, mensaje fijo,
    `__cause__` y `__context__` nulos, ningún centinela en el traceback
    formateado y ninguna espera con una excepción activa; el agotamiento de
    reintentos por red tampoco conserva contexto;
  - (c) una cookie de respuesta no se envía en la request siguiente ni queda en
    el jar, y una prueba de control demuestra que el harness sí la guardaría
    sin la política; la sesión HTTP no usa credenciales `.netrc` del entorno;
  - (d) un `Retry-After` por encima del tope levanta `TransportError` sin
    esperar antes del último intento, `nan` o negativo usa el backoff y uno en
    formato fecha HTTP se respeta.

  Una mutación que revierte cada protección hace fallar su prueba. En el
  runner, un `302` de ClubDIA produce `authentication_required`. Vinculado con
  `REQ-007`.
- `AC-009`: el manifest de una corrida contiene los campos v2; requests,
  reintentos y códigos por componente coinciden con lo que vio el transporte
  falso; `published` refleja lo publicado; cambiar la ruta del archivo de
  sesión o su contenido no cambia el hash y cambiar un valor HTTP público sí.
  Vinculado con `REQ-008`.
- `AC-010`: cada línea de log de una corrida, capturada en un stream
  inyectado, es JSON con `run_id` y `store`, y los eventos de componente
  incluyen `component`. Ningún centinela de cookies, headers o token aparece
  en esa salida ni en `caplog.text`, incluso con excepciones encadenadas. Una
  excepción inesperada en la CLI se registra sólo por tipo y devuelve `1`.
  Vinculado con `REQ-009`.
- `AC-011`: `session.py` no contiene referencias a ClubDIA; la extracción del
  HAR vive en el paquete DIA; el script propone `.secrets/dia-session.json` y
  rechaza `output/`; `.gitignore` y `.dockerignore` ignoran `.secrets/`; con un
  `.secrets/dia-session.json` en el directorio de trabajo y sin variable,
  ClubDIA queda en `authentication_required` con el mensaje accionable.
  Vinculado con `REQ-010`.
- `AC-012`: ADR-0003 está aceptado y enlazado; pytest, Ruff y los validadores
  del repositorio pasan en Windows, y CI pasa en el pull request. Vinculado con
  `REQ-011`.
