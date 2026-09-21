# Plan de implementación

## Diseño

- `DES-001`: usar `docs/platforms/<plataforma>/README.md` como ficha común y
  `versions/<version>.md` como anexos para separar capacidades compartidas de
  diferencias de API.
- `DES-002`: usar los estados `draft`, `active` y `retired`, junto con
  `last_verified`, para distinguir descubrimiento, información reutilizable e
  historial.
- `DES-003`: exigir metadata y encabezados mínimos mediante el validador, sin
  interpretar contenido externo ni consultar APIs.

## Contratos

Una ficha de plataforma tiene metadata `id`, `status`, `created`, `updated` y
`last_verified`. Un anexo tiene `platform`, `version`, `status`, `created`,
`updated` y `last_verified`. Los estados permitidos son `draft`, `active` y
`retired`; `pending` sólo es válido como `last_verified` durante `draft`.

Los directorios de plataforma y archivos de versión usan slugs kebab-case. Cada
plataforma contiene `README.md` y `versions/`; este último puede quedar vacío
mientras la exploración no haya identificado una versión de API.

## Flujo de datos

Durante el descubrimiento, la iniciativa SDD crea o actualiza una ficha `draft`.
Los hallazgos con fuente y fecha pasan a las secciones confirmadas; las hipótesis
permanecen en hallazgos pendientes. Cuando la información se puede reutilizar,
la ficha pasa a `active` y recibe una fecha de verificación. Cada cambio de API
actualiza o crea su anexo de versión, y las versiones que dejan de aplicar pasan
a `retired`.

## Fallos y recuperación

Una ficha sin overview, directorio de versiones, metadata o secciones mínimas
falla en el validador con un mensaje que identifica el archivo. La validación no
afirma que una fuente externa siga vigente; la guía exige revisión manual y
fecha de última verificación.

## Pruebas

- Validar una ficha `draft` y un anexo con las secciones y metadata correctas
  para `REQ-001` a `REQ-003`.
- Validar que una ficha incompleta falle de forma accionable para `REQ-005`.
- Ejecutar el self-test del validador y las comprobaciones habituales para
  `AC-004`.
- Verificar enlaces desde README, contribución y SDD para `AC-005`.

## Despliegue

El catálogo queda disponible al fusionar esta iniciativa. No necesita migración
ni rollback de datos. Revertir el cambio restaura el flujo documental previo.
