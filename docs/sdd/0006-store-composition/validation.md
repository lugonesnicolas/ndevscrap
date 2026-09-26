# Validación

## Resultado

Iniciativa en `in-progress`: especificación y plan aprobados por el usuario el
2026-09-26; implementación en curso.

## Evidencia

- Base: `952fc1d` sobre `main` `96594b0`, rama `feat/0006-store-composition`.
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
  interpolación de los mensajes de calidad. No requiere otra pasada; la QA de
  seguridad verificará redirects y cookies sobre el código.

## Criterios de aceptación

- `AC-001`: pendiente.
- `AC-002`: pendiente.
- `AC-003`: pendiente.
- `AC-004`: pendiente.
- `AC-005`: pendiente.
- `AC-006`: pendiente.
- `AC-007`: pendiente.
- `AC-008`: pendiente.
- `AC-009`: pendiente.
- `AC-010`: pendiente.
- `AC-011`: pendiente.
- `AC-012`: pendiente.

## Desviaciones

Ninguna por ahora.
