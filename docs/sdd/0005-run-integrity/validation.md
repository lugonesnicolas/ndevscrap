# Validación

## Resultado

Implementación completa y validada localmente en Windows el 2026-09-26 sobre la
base `345339f` con cambios sin versionar en `feat/0005-run-integrity`. La
iniciativa queda en `validation` hasta registrar la ejecución verde de CI
(Ubuntu) del pull request; con esa evidencia puede pasar a `done`.

## Evidencia

- Reproducción previa a la especificación (2026-09-25, `345339f`, fuera del
  repositorio): tres llamadas consecutivas a `FileSnapshotStore.publish()`
  confirmaron la línea base tomada del intento fallido, el reemplazo del
  snapshot fechado válido y la procedencia inconsistente de current.
- Revisión de arquitectura de la especificación (2026-09-26): primera pasada
  `not-ready` con tres bloqueantes (raw inválido o truncado reutilizado al
  reanudar, salidas normalizadas heredadas en staging y procedencia no
  verificable) y siete a corregir; segunda pasada `ready-with-conditions` sin
  bloqueantes. Todo se incorporó a la especificación y al plan antes de
  implementar. Por decisión del usuario, los intentos se guardan en el árbol
  hermano `attempts/<fecha>/<run_id>/` y sólo los fallos transitorios conservan
  el staging.
- `TASK-001`: con las pruebas nuevas y el código de la base, `uv run pytest`
  terminó con 27 fallos y 28 pruebas correctas.
- Pruebas de mutación locales (plugins en un directorio temporal, sin cambios
  en el repositorio):
  - restaurar la línea base tomada del último intento hace fallar
    `test_quarantined_runs_do_not_poison_the_volume_baseline` (C se publica);
  - desactivar la reversión de la promoción hace fallar
    `test_failed_promotion_restores_snapshot_and_current[.current-]`;
  - desactivar la reescritura de rutas al archivar hace fallar cuatro pruebas
    de procedencia del runner.
- Revisión QA independiente (2026-09-26): `not-ready` por un defecto real
  (fallo del reemplazo de current después de promover dejaba `<fecha>/` e
  índice inconsistentes), evidencia de cierre pendiente y aserciones de
  procedencia que no distinguían corridas con reloj fijo. Se corrigieron el
  orden de publicación con reversión completa, el reloj de pruebas, la
  verificación del `run_id` del manifest de origen y las brechas menores
  (hash de todo `<fecha>/`, reintentos fallidos transitorio y estructural, dos
  particiones al reanudar, cero productos, contadores del catálogo, reintentos
  en `finally`, limpieza de temporales y `.current-*`, nombre `superseded-*`
  con el reloj de la corrida, campos del índice y redacción del README).
- Revisión de seguridad independiente (2026-09-26): sin bloqueantes. Se
  incorporaron mensajes fijos para los fallos de sesión de ClubDIA, centinelas
  para token ausente, sesión sin `order-form-id`, archivo malformado y causa
  encadenada que llega al límite del componente, y la verificación de clave en
  `read_raw()`.
- Verificación final en Windows 11, Python 3.12.14 administrado por uv
  0.12.18, árbol sin versionar sobre `345339f`:
  - `uv sync --all-groups`: OK.
  - `uv run pytest`: 64 pruebas correctas (con `--basetemp` fuera del
    repositorio y `-p no:cacheprovider`).
  - `uv run ruff check .`: OK.
  - `uv run ruff format --check .`: OK, 63 archivos.
  - `python scripts/validate_repository.py`: OK.
  - `python scripts/validate_repository.py --self-test`: OK.
- CI Ubuntu del pull request: pendiente.

## Criterios de aceptación

- `AC-001`: satisfecho por
  `test_quarantined_runs_do_not_poison_the_volume_baseline` (N=20, B y C con
  11, error "from 20", hash de current igual a A) y por las pruebas de
  almacenamiento de manifest heredado de un intento fallido, índice corrupto o
  ajeno e índice sin entrada `catalog`.
- `AC-002`: satisfecho por `_assert_current_provenance` en las pruebas del
  runner (hash de current, hash del origen y `run_id` del manifest de origen,
  con reloj que avanza) incluida la secuencia de corridas aceptadas con sesión
  vencida, y por la entrada `legacy` con origen nulo.
- `AC-003`: satisfecho por el hash de todo `<fecha>/` tras reintentos en
  cuarentena, transitorios y estructurales, por el archivado del snapshot
  aceptado previo y por la restauración ante fallos de renombrado del staging o
  de reemplazo de current.
- `AC-004`: satisfecho por
  `test_transient_failure_keeps_staging_and_resumes_confirmed_pages`: dos
  particiones, fallo en la página 4 de la segunda, reanudación que pide el
  árbol y sólo `almacen:1`, `bebidas:1` y `bebidas:4`, 40 filas publicadas y
  sin cupones del intento previo; y por la limpieza del staging al reanudar.
- `AC-005`: satisfecho por la página rechazada guardada en
  `attempts/<fecha>/<run_id>/rejected/`, ausente de `raw/` y vuelta a pedir, por
  el gzip truncado vuelto a pedir y por la clave de raw colisionada.
- `AC-006`: satisfecho por los tres escenarios de ClubDIA con catálogo válido
  (contadores iguales a la corrida base) y por el catálogo fallido con ClubDIA
  exitoso publicado desde `attempts/`.
- `AC-007`: satisfecho por `test_retries_are_attributed_to_each_component` y
  por el catálogo fallido que informa sus tres reintentos.
- `AC-008`: satisfecho por
  `test_session_material_never_reaches_output_or_logs` con ocho variantes,
  captura `DEBUG` y lectura de todo archivo de salida, incluidos los gzip.
- `AC-009`: satisfecho localmente por `tests/test_cli.py` (códigos `0`, `2` y
  `1`, campo `snapshot`, error de configuración y de almacenamiento) y por la
  verificación en Windows; pendiente la ejecución de CI en Ubuntu.

## Desviaciones

- Las páginas VTEX de las pruebas de extremo a extremo se generan con la forma
  de `tests/fixtures/vtex/product_page.json` en lugar de leer la fixture, para
  escalar el volumen por escenario. La fixture sigue cubriendo la
  normalización en `tests/test_vtex_connector.py`.
- Además de lo planificado se agregó la verificación de clave en `read_raw()`
  y la limpieza de temporales y `.current-*`, a partir de las revisiones QA y de
  seguridad.
- Riesgos aceptados y derivados a `0006-store-composition`, fuera del alcance
  de esta iniciativa y previos a ella:
  - el transporte reenvía cookies y headers de sesión si una respuesta
    redirige a otro host;
  - errores de construcción de la request como `InvalidHeader` se reintentan
    como transitorios y su texto encadenado puede contener el valor del header
    si el proceso se interrumpe durante la espera;
  - catálogo y ClubDIA comparten el cookie jar del transporte.
- Riesgos operativos registrados sin cambios: crecimiento de `attempts/` sin
  retención, ausencia de bloqueo entre corridas concurrentes, descenso acumulado
  de la línea base y recuperación de `.current.backup` tras un proceso
  terminado durante el reemplazo.
