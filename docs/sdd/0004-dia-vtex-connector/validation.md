# Validación

## Resultado

Validación técnica completada el 2026-09-25. La corrida local completa para CP
`1806` publicó catálogo y ClubDIA correctamente. El cierre operativo de la
iniciativa permanece pendiente de documentar la referencia formal de
autorización, los límites autorizados y el contacto técnico.

## Evidencia

- Revisión documental y aprobación: aprobada por el usuario el 2026-09-23.
- Descubrimiento público autorizado: Intelligent Search v1, árbol de categorías,
  cuenta `diaio`, parámetros `zip-code` y `sc`, 5.496-5.498 productos observados
  y límite de 50 páginas por partición confirmados el 2026-09-23.
- Descubrimiento ClubDIA autorizado mediante HAR el 2026-09-25: token efímero
  por `GET /token-by-user` y 9 cupones por `GET /cupons`, sin persistir raw
  autenticado, identidad, token ni carrito.
- `python scripts/validate_repository.py`: OK el 2026-09-25 usando el runtime
  Python 3.12.14 administrado por uv.
- `python scripts/validate_repository.py --self-test`: OK el 2026-09-25.
- `uv 0.12.18` instalado mediante el instalador oficial de Astral.
- `uv sync --all-groups`: OK; lockfile generado y entorno sincronizado.
- `uv run pytest`: 24 pruebas correctas con directorio temporal dentro de
  `output/` para respetar los permisos del entorno.
- `uv run ruff check .`: OK.
- `uv run ruff format --check .`: OK.
- CLI local `ndevscrap --help` y `ndevscrap run --help`: OK.
- Docker Desktop 4.90.0 / Engine 29.7.2: imagen `ndevscrap:local` construida y
  entry point verificado el 2026-09-25.
- Corrida completa autorizada para CP `1806`: estado `success`, 5.533 productos,
  9 cupones, cero reintentos y cero errores. El snapshot real quedó bajo
  `output/`, ignorado por Git.
- Escaneo de outputs publicables: sin marcadores de cookies, tokens, email,
  documento ni `order-form-id`.

## Criterios de aceptación

- `AC-001`: satisfecho por fixtures VTEX y pruebas de normalización multipágina.
- `AC-002`: satisfecho por pruebas de reemplazo diario, current y checkpoints.
- `AC-003`: satisfecho por pruebas de `Retry-After`, `429` y autenticación.
- `AC-004`: satisfecho por pruebas de sesión vencida y conservación de cupones.
- `AC-005`: satisfecho por pruebas de cero, rechazos y caída de volumen.
- `AC-006`: satisfecho por fixture ClubDIA con PII señuelo y salida allowlisted.
- `AC-007`: satisfecha por CLI local, build Docker y entry point de la imagen.
- `AC-008`: satisfecha por validadores, 24 pruebas, Ruff, Docker y smoke real.

## Desviaciones

- En Windows, `zoneinfo` requirió declarar `tzdata`; se agregó como dependencia
  portable y el smoke posterior finalizó correctamente.
- El endpoint `PUT /cupons` observado en el checkout no lista beneficios. La
  pantalla ClubDIA usa `GET /cupons` con token y `order-form-id`; el SDD y el
  conector se ajustaron a ese flujo de sólo lectura.
- Hallazgos posteriores al cierre técnico (auditoría v0.1.0 del 2026-09-25):
  la línea base de volumen se leía del último intento y no del current
  publicado, `current/manifest.json` no describía los datos de current, un
  reintento fallido reemplazaba el snapshot válido del día y descartaba el
  staging reanudable, y una excepción no prevista de ClubDIA marcaba el catálogo
  como fallido. Por ello `AC-002`, `AC-004` y `AC-005` se consideraban
  satisfechos sólo parcialmente. La corrección se especifica y valida en
  [0005-run-integrity](../0005-run-integrity/spec.md): los manifests de intentos
  no aceptados pasan a `attempts/<fecha>/<run_id>/` y `current/manifest.json` es
  ahora un índice de procedencia.
- La auditoría también encontró brechas en `REQ-003` (el catálogo se acumulaba
  completo en memoria), `REQ-008` (timeout, ritmo y reintentos no eran
  configurables) y `REQ-009` (el manifiesto no informaba requests, códigos HTTP
  ni duración por componente, y no había logs estructurados). Se cierran en
  [0006-store-composition](../0006-store-composition/spec.md) con normalización
  en streaming, variables `NDEVSCRAP_HTTP_*`, manifest v2 y logs JSON.
