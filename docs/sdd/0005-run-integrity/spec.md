---
id: 0005-run-integrity
title: Integridad de snapshots, línea base de calidad y aislamiento de componentes
status: done
owner: maintainers
created: 2026-09-26
updated: 2026-09-26
approval: user-approved-2026-09-26
---

# Especificación

## Problema

La auditoría de v0.1.0 sobre `345339f` detectó que la implementación de
[0004-dia-vtex-connector](../0004-dia-vtex-connector/spec.md) no cumple
plenamente `DES-005`, `DES-006`, `DES-007`, `AC-002`, `AC-004` y `AC-005`. Una
reproducción local con `FileSnapshotStore` y tres corridas consecutivas mostró:

1. Corrida A publica 5.533 productos. Corrida B produce 3.000, queda en
   cuarentena y conserva `current/products.jsonl`, pero reemplaza
   `current/manifest.json` y el snapshot fechado válido del día por su intento
   fallido.
2. Corrida C lee 3.000 como línea base porque `previous_product_count()` usa el
   manifest del último intento, supera el control de caída y publica un
   catálogo 46% menor.

Además:

- `current/manifest.json` describe la última corrida y no los datos que
  realmente contiene `current/`.
- `publish()` se ejecuta aun ante un fallo técnico, mueve el staging y elimina
  la posibilidad de reanudar desde las páginas raw confirmadas.
- El raw se guarda antes de normalizar y sin escritura atómica: una página con
  estructura inesperada o un gzip truncado quedarían en staging y harían fallar
  cada reanudación.
- Una excepción no prevista en ClubDIA cae en el manejador global y marca el
  catálogo como `failed` aunque ya hubiera superado calidad.
- `ComponentResult.retries` de ClubDIA incluye los reintentos del catálogo y
  un catálogo fallido informa cero reintentos.
- No existen pruebas de extremo a extremo del runner ni de la CLI que
  detecten estas regresiones.

## Objetivos

- Garantizar que current sólo cambie con datos que superaron calidad y que su
  procedencia sea verificable por componente mediante hash y ruta durable.
- Conservar el snapshot fechado válido frente a reintentos del mismo día y
  retener la evidencia de cada intento, incluido un snapshot válido reemplazado.
- Permitir la reanudación después de un fallo transitorio sin arrastrar datos
  estructuralmente inválidos ni salidas de un intento anterior.
- Aislar los componentes para que un fallo de ClubDIA nunca altere el catálogo
  ni exponga material de sesión en logs.
- Cubrir estos comportamientos con pruebas deterministas de extremo a extremo.

## Alcance

Incluye `FileSnapshotStore`, el protocolo `SnapshotStore` en lo necesario para
comunicar el desenlace del catálogo, el orquestador `run_dia`, puntos de
inyección de transporte y reloj para pruebas, el mensaje de error de
almacenamiento de la CLI, pruebas de runner, CLI y almacenamiento, y la
documentación mínima del layout de salida.

Excluye la generalización del runner y del `SnapshotStore` por componente, el
esquema v2 del `RunManifest`, la normalización en streaming, la configuración
HTTP por entorno, los logs estructurados (todo ello en `0006-store-composition`),
la recuperación automática de un reemplazo de directorio interrumpido, la
política de retención de intentos, el bloqueo entre corridas concurrentes, la
limpieza de staging de días anteriores y cualquier cambio de umbrales, nombres
de archivo de current, interfaz CLI o códigos de salida.

## Requisitos

- `REQ-001`: la línea base de volumen del catálogo debe provenir del último
  catálogo publicado en `current/`, nunca de un intento no publicado. Si el
  índice de current falta, está corrupto, es de formato anterior o no tiene
  entrada de catálogo, se usa la cantidad de filas de `current/products.jsonl`;
  si el archivo tampoco existe, se considera primera corrida.
- `REQ-002`: `current/manifest.json` debe ser un índice identificado como tal
  que registre, por componente presente en current, `run_id`, `snapshot_id`,
  fecha de publicación, cantidad de registros, `sha256`, archivo de current y
  ruta durable de origen; y un resumen separado del último intento que no
  altere esa procedencia. Un current heredado del formato anterior se registra
  con procedencia `legacy`, sin atribuirle `run_id` ni ruta de origen.
- `REQ-003`: el snapshot fechado `<fecha>/` sólo debe reemplazarse cuando el
  catálogo supera calidad. Todo intento no aceptado y todo snapshot válido
  reemplazado deben conservarse en el árbol hermano
  `attempts/<fecha>/<run_id>/` del mismo store y ubicación.
- `REQ-004`: sólo un fallo transitorio del catálogo (red, timeout, `429` o
  `5xx` agotados) debe conservar `.staging-<fecha>` para reanudar. Al reanudar,
  el staging se limpia salvo `raw/` y `checkpoint.json`, y las páginas raw
  confirmadas se reutilizan sin volver a pedirlas. Un fallo estructural o de
  configuración mueve el staging a `attempts/` y la siguiente corrida parte de
  cero.
- `REQ-005`: una página raw sólo debe confirmarse en staging después de
  normalizarse sin error, mediante escritura atómica; un raw ilegible se trata
  como ausente. Una página que no normaliza se conserva como evidencia en una
  ubicación que nunca se reutiliza para reanudar.
- `REQ-006`: catálogo y ClubDIA deben ejecutarse con aislamiento de errores.
  ClubDIA se intenta aunque el catálogo falle, y ninguna excepción de ClubDIA
  puede modificar estado, contadores ni publicación del catálogo.
- `REQ-007`: los reintentos del manifest deben atribuirse al componente que los
  produjo, también cuando el componente falla.
- `REQ-008`: ningún archivo bajo el directorio de salida ni ningún log de la
  corrida debe contener material de sesión, incluso cuando una excepción
  encadenada lo contiene; los fallos de ClubDIA se registran sólo con tipo de
  excepción y mensaje fijo, sin traceback.
- `REQ-009`: la interfaz `ndevscrap run dia --postal-code <CP> --output <dir>`,
  los códigos de salida `0`, `1` y `2`, la forma de la línea JSON final, los
  nombres `products.jsonl` y `coupons.jsonl` de current y los umbrales de 0%,
  5% y 30% no cambian. El campo `snapshot` de esa línea apunta al snapshot
  fechado si el catálogo fue aceptado o al directorio del intento en otro caso.

## Restricciones

- Sigue ADR-0001 y ADR-0002 y el contrato de 0004. No se agrega ADR porque se
  restaura semántica aprobada; la decisión transversal sobre publicación por
  componente se registrará como ADR en `0006-store-composition`, donde se
  generalizan `SnapshotStore` y `RunManifest`.
- La suite permanece determinista y sin acceso a red; transporte y reloj se
  inyectan.
- Un `current/manifest.json` de formato anterior o corrupto debe leerse sin
  error.
- La suite de almacenamiento y runner debe ejecutarse también en Windows, que
  es la plataforma operativa local.
- Sin corridas reales en esta iniciativa; la evidencia operativa se obtiene en
  `0008-release-v0-1-0`.

## Criterios de aceptación

- `AC-001`: en una secuencia A (N válidos), B (0,55·N) y C (0,55·N) con N
  escalado para fixtures, B y C quedan en cuarentena, `current/products.jsonl`
  conserva el hash de A y la línea base usada por C es N. Un índice corrupto o
  heredado que describe un intento fallido usa el conteo de filas publicado.
  Vinculado con `REQ-001`.
- `AC-002`: tras cualquier corrida, el `sha256` de cada archivo de current
  coincide con el del índice; para entradas con procedencia `run`, además, su
  ruta de origen existe con el mismo hash, incluida la secuencia "A aceptada
  con cupones, B aceptada con sesión vencida". Las entradas `legacy` tienen
  origen nulo. Vinculado con `REQ-002`.
- `AC-003`: un reintento en cuarentena o fallido el mismo día no modifica los
  bytes de `<fecha>/` válido y deja su evidencia en `attempts/<fecha>/<run_id>/`;
  un reintento aceptado archiva el snapshot válido anterior en
  `attempts/<fecha>/<run_id-anterior>/`. Vinculado con `REQ-003`.
- `AC-004`: una corrida cuyo catálogo agota reintentos en la página K de una
  partición conserva el staging; la siguiente corrida del día vuelve a pedir el
  árbol de categorías y la página 1 de cada partición, no vuelve a pedir las
  páginas 2..K-1 confirmadas y publica el catálogo completo. Una salida
  normalizada de cupones del intento anterior no aparece en el snapshot
  reanudado. Vinculado con `REQ-004`.
- `AC-005`: una página con estructura inesperada en la posición K no queda en
  `raw/` de ningún staging reutilizable, sí queda como evidencia rechazada en
  `attempts/<fecha>/<run_id>/`, y la corrida siguiente la vuelve a pedir. Un
  gzip truncado en staging se vuelve a pedir en lugar de fallar.
  Vinculado con `REQ-004` y `REQ-005`.
- `AC-006`: con catálogo válido, ClubDIA `401`, sesión ausente o una excepción
  no prevista en ClubDIA producen `partial_success`, catálogo publicado y
  cupones de current preservados. Con catálogo en cuarentena o fallido y
  ClubDIA exitoso, la corrida es `failed`, los cupones se publican con origen
  durable en `attempts/` y la procedencia del catálogo en current no cambia.
  Vinculado con `REQ-006`.
- `AC-007`: los reintentos del catálogo no aparecen en ClubDIA y viceversa, y
  un catálogo fallido informa los reintentos que consumió. Vinculado con
  `REQ-007`.
- `AC-008`: valores centinela de cookies, headers y token, incluidos en la
  causa encadenada de una excepción de ClubDIA, no aparecen en ningún archivo
  de salida ni en `caplog.text`. Vinculado con `REQ-008`.
- `AC-009`: la CLI devuelve `0`, `2` y `1` para éxito, éxito parcial y fallo o
  configuración inválida, y el campo `snapshot` sigue `REQ-009`; pytest, Ruff y
  los validadores del repositorio finalizan correctamente en Windows y en CI.
  Vinculado con `REQ-009`.
