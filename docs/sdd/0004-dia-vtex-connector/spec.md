---
id: 0004-dia-vtex-connector
title: Conector escalable de DIA Online sobre VTEX
status: in-progress
owner: maintainers
created: 2026-09-23
updated: 2026-09-25
approval: user-approved-2026-09-23
---

# Especificación

## Problema

NDevScrap todavía no tiene CLI, contratos ejecutables ni conectores. Se necesita
extraer diariamente el catálogo, precios públicos y cupones personalizados
autorizados de DIA Online para una ubicación piloto, sin acoplar la solución a
una tienda ni comprometer secretos o datos personales.

La evidencia preliminar indica que el storefront utiliza VTEX, pero antes de
implementar deben confirmarse mediante tráfico autorizado los endpoints, la
paginación, el contexto geográfico, el canal de venta y la sesión requerida por
ClubDIA. Los hallazgos reutilizables se mantendrán en la
[ficha de VTEX](../../platforms/vtex/README.md).

## Objetivos

- Crear contratos reutilizables para adquisición, conectores, sesiones y
  persistencia de snapshots.
- Incorporar un conector de plataforma VTEX y configuración específica para DIA
  Online sin usar navegador durante la operación normal.
- Exponer una CLI portable para ejecución local y en Docker.
- Preservar snapshots diarios idempotentes en capas raw, normalized y current.
- Capturar metadata de cupones ClubDIA con una sesión autorizada sin almacenar
  identidad, credenciales ni respuestas autenticadas completas.
- Detectar fallos técnicos, expiración de sesión y degradaciones de calidad sin
  invalidar resultados públicos correctos.

## Alcance

Incluye descubrimiento autorizado de las APIs usadas por el storefront,
catálogo, productos, SKU, precios, disponibilidad, promociones públicas,
cupones personalizados de sólo lectura, código postal piloto, archivos JSONL,
raw público comprimido, manifiestos, CLI, Docker, observabilidad básica y
pruebas deterministas con fixtures sanitizadas.

El código postal piloto queda fijado en `1806`; la CLI lo usa como valor
predeterminado y lo conserva en cada observación.

Excluye login automatizado, activación de cupones, carrito, checkout, compras,
órdenes, perfiles, descarga de imágenes, evasión de controles, Playwright en el
runtime, múltiples ubicaciones, scheduler interno, PostgreSQL, almacenamiento
cloud, colas distribuidas y microservicios.

## Requisitos

- `REQ-001`: la ejecución debe aceptar tienda DIA, código postal y directorio de
  salida mediante una CLI estable, con configuración tipada y sin secretos en
  argumentos o archivos versionados.
- `REQ-002`: los límites `Connector`, `Transport`, `SessionProvider` y
  `SnapshotStore` deben permitir sustituir plataforma, transporte, sesión y
  persistencia sin modificar el orquestador.
- `REQ-003`: el conector VTEX debe descubrir y extraer el catálogo completo por
  páginas o cursores, conservar checkpoints y normalizar productos y SKU sin
  cargar el catálogo entero en memoria.
- `REQ-004`: cada producto normalizado debe conservar identidad de producto y
  SKU, GTIN cuando exista, nombre, marca, categorías, URL, imágenes como URLs,
  seller, disponibilidad, precios exactos en ARS, promoción, ubicación,
  timestamps y procedencia.
- `REQ-005`: la integración ClubDIA debe leer una sesión provista externamente,
  persistir sólo metadata permitida de cupones y clasificar `401` o `403` como
  expiración que requiere intervención.
- `REQ-006`: las respuestas públicas originales deben almacenarse comprimidas y
  los productos, cupones y manifiestos como snapshots diarios JSONL/JSON, con
  publicación atómica de una vista current.
- `REQ-007`: una repetición para la misma tienda, ubicación y fecha debe ser
  idempotente y reanudable desde checkpoints sin duplicar observaciones.
- `REQ-008`: el transporte debe aplicar timeout, una solicitud por segundo,
  concurrencia uno, hasta tres reintentos con backoff y jitter, y respetar
  `Retry-After`; todos esos valores deben ser configurables.
- `REQ-009`: la ejecución debe emitir logs y un manifiesto con `run_id`, versión,
  hash de configuración sin secretos, conteos, duración, reintentos, errores y
  estado independiente para catálogo y ClubDIA.
- `REQ-010`: current no debe actualizarse si el catálogo produce cero productos,
  supera 5% de registros inválidos o cae más de 30% respecto del último snapshot
  válido; la comparación histórica no aplica a la primera corrida.
- `REQ-011`: una sesión ClubDIA vencida debe permitir publicar el catálogo
  público válido, marcar la corrida parcial y conservar el último current de
  cupones.
- `REQ-012`: la misma interfaz debe ejecutarse con Python 3.12 en local y dentro
  de una imagen Docker, delegando la programación diaria al host.
- `REQ-013`: la suite habitual debe ser determinista, no consultar DIA ni VTEX y
  cubrir parsing, paginación, errores, seguridad, calidad e idempotencia con
  fixtures locales sanitizadas.

## Restricciones

- La implementación sigue ADR-0001 y ADR-0002: monolito modular, composición y
  API-first; no se agrega un ADR nuevo mientras esos límites no cambien.
- El smoke test y la ejecución completa requieren sesión local y autorización
  aplicable. El código postal es `1806`; los límites permitidos y el contacto
  técnico deben documentarse fuera de Git antes de programar producción.
- No se registran cookies, tokens, usuario, contraseña, perfil, carrito ni otros
  datos personales. Las respuestas autenticadas completas no se persisten.
- Los importes usan `Decimal` y se serializan como cadenas; no se usa `float`.
- Si el descubrimiento no confirma una API HTTP suficiente, esta iniciativa
  vuelve a `draft` antes de proponer un adaptador de navegador.
- Los resultados generados permanecen en `output/` y no se versionan.

## Criterios de aceptación

- `AC-001`: una fixture VTEX multipágina produce todos los productos y SKU en el
  contrato normalizado con precios exactos, procedencia y ubicación.
- `AC-002`: dos ejecuciones equivalentes para la misma fecha dejan un único
  snapshot lógico válido y current se publica atómicamente.
- `AC-003`: respuestas transitorias y `429` ejercitan reintentos y
  `Retry-After`; errores permanentes y de autenticación no generan bucles.
- `AC-004`: una sesión vencida produce estado parcial, publica catálogo válido y
  no reemplaza el último current de cupones.
- `AC-005`: cero productos, más de 5% de rechazos o una caída mayor a 30% impiden
  actualizar current y quedan diagnosticados en el manifiesto.
- `AC-006`: logs, fixtures, manifests y snapshots no contienen secretos ni datos
  de perfil, y ClubDIA sólo expone la allowlist de metadata acordada.
- `AC-007`: la CLI documentada funciona con la misma interfaz en local y Docker,
  y la configuración de sesión proviene de un archivo externo.
- `AC-008`: el validador del repositorio, pytest y Ruff finalizan correctamente,
  y un smoke test autorizado registra evidencia reproducible sin versionar la
  respuesta real.
