# Plan de implementación

## Diseño

- `DES-001`: implementar un monolito modular con un orquestador independiente de
  los adaptadores `Connector`, `Transport`, `SessionProvider` y `SnapshotStore`,
  en línea con ADR-0001.
- `DES-002`: modelar VTEX como conector de plataforma y DIA como configuración y
  composición de capacidades; ClubDIA permanece como adaptador específico de la
  tienda.
- `DES-003`: confirmar mediante tráfico autorizado la API usada por el
  storefront y elegir Intelligent Search o Legacy Search según evidencia. Si
  ambas son suficientes, preferir la usada actualmente por la tienda.
- `DES-004`: usar exclusivamente HTTP en el runtime. El descubrimiento puede
  observar la red del navegador, pero no incorpora automatización ni evade
  desafíos.
- `DES-005`: escribir en streaming raw público comprimido, JSONL normalizado y
  un manifiesto por snapshot; publicar current mediante reemplazo atómico sólo
  después de superar controles de calidad.
- `DES-006`: tratar catálogo público y ClubDIA como componentes con estados
  separados. Un fallo de sesión produce `partial_failure`, no invalida catálogo
  válido y no reemplaza cupones current.
- `DES-007`: identificar un snapshot lógico por tienda, ubicación y fecha local;
  conservar un `run_id` por intento y checkpoints reanudables por página o
  cursor.

## Contratos

La CLI pública será:

```text
ndevscrap run dia --postal-code <CP> --output <directorio>
```

`NDEVSCRAP_DIA_SESSION_FILE` apuntará a un archivo no versionado con la sesión
ya autenticada. La CLI aceptará ejecución pública sin sesión para diagnóstico,
pero una corrida configurada con ClubDIA quedará parcial si la sesión falta o
expiró.

Para DIA, el archivo contiene cookies VTEX funcionales y el `order-form-id`
efímero. El código postal predeterminado y piloto es `1806`.

Los contratos compartidos serán síncronos en esta versión:

- `Connector.discover(context)`, `extract(item, context)` y
  `normalize(record)` para adquisición y transformación.
- `Transport.request(request)` para HTTP, límites y reintentos.
- `SessionProvider.load()` para material secreto de corta duración, sin
  persistencia ni logging.
- `SnapshotStore` para raw público, normalized, checkpoints, manifests y
  publicación atómica de current.

`ProductSnapshot` tendrá identificadores como strings, `Decimal` para importes y
campos explícitos de ubicación, moneda, timestamps y procedencia.
`CouponSnapshot` tendrá sólo identificador, título, descripción, tipo y valor,
vigencia, condiciones, alcance, productos o categorías y estado. El esquema y
el conector tendrán versiones propias.

La configuración pública declarará dominio, país `ARG`, moneda `ARS`, locale,
zona `America/Argentina/Buenos_Aires`, código postal, timeout, ritmo, reintentos,
page size y salida. `.env.example` documentará nombres, nunca valores secretos.

## Flujo de datos

1. La CLI valida configuración, crea `run_id` y clave lógica diaria, y carga el
   último manifest válido sin leer secretos para calcular el hash.
2. El cliente VTEX establece el contexto autorizado de código postal y canal de
   venta confirmado durante el descubrimiento.
3. El conector recorre páginas o cursores, guarda cada respuesta pública como
   gzip, actualiza checkpoint y emite productos normalizados en streaming.
4. El cliente ClubDIA carga la sesión desde el archivo externo, obtiene un token
   efímero mediante `GET /_v/private/club-dia/_v1/token-by-user` y consulta los
   cupones mediante `GET /_v/private/club-dia/_v1/cupons` con `order-form-id`.
   Proyecta directamente a la allowlist sin persistir token, carrito ni raw
   autenticado.
5. Los validadores calculan rechazos, volumen, diferencias con el snapshot
   anterior y estado por componente.
6. Los archivos temporales se sincronizan y reemplazan el snapshot diario. Sólo
   los componentes válidos actualizan su vista current.
7. Se escribe el manifest final y la CLI devuelve éxito, fallo o éxito parcial
   con códigos documentados.

La salida se organiza por tienda, ubicación y fecha con directorios `raw/`,
`normalized/` y `current/`. Las imágenes se conservan como URLs; no se
descargan. No habrá borrado automático en esta versión.

## Fallos y recuperación

- Timeouts, fallos de red, `429` y `5xx` recuperables se reintentan hasta tres
  veces con backoff, jitter y `Retry-After`; el checkpoint evita repetir páginas
  confirmadas al reanudar.
- Configuración inválida, esquemas incompatibles y errores permanentes fallan
  sin publicar current.
- `401` y `403` de ClubDIA no se reintentan: se redacta el contexto, se conserva
  el current anterior y se marca intervención requerida.
- La escritura ocurre en archivos temporales dentro del destino final y usa
  reemplazo atómico. Un proceso interrumpido no expone un current incompleto.
- Los controles de cero productos, rechazos mayores a 5% y caída mayor a 30%
  ponen el catálogo en cuarentena; el manifest conserva evidencia y el último
  current queda intacto.
- La ausencia de un snapshot anterior desactiva únicamente la comparación de
  caída de volumen.

## Pruebas

- Fixtures públicas multipágina para variantes, EAN ausente, categorías,
  sellers, sin stock, promociones y precios decimales.
- Fixtures autenticadas sanitizadas para la allowlist de cupones, respuesta
  vacía, sesión válida y `401/403`, sin identidad ni cookies reales.
- Tests de contrato para cada protocolo y tests del transporte para timeout,
  `Retry-After`, backoff y agotamiento.
- Tests del almacenamiento para gzip, JSONL estable, checkpoints, reemplazo
  atómico, idempotencia diaria y recuperación ante temporales incompletos.
- Tests de calidad para cero productos, 5% de rechazos, caída de 30%, primera
  corrida y separación catálogo/ClubDIA.
- Tests de CLI en local y Docker con transporte simulado; ninguna prueba
  determinista consulta servicios externos.
- Smoke autorizado sobre muestra pequeña y luego catálogo completo, registrando
  sólo conteos, hashes y tiempos en `validation.md`.

## Despliegue

La iniciativa comienza en `draft`. Después de confirmar descubrimiento,
permisos, límites y contratos se aprueban `spec.md` y este plan, y el estado pasa
a `approved` antes de implementar. Al comenzar código cambia a `in-progress`.

La entrega incluye paquete Python 3.12, entry point de CLI, Dockerfile y guía
para invocación manual o desde un scheduler del host. El despliegue inicial es
local y Docker; no hay migración de datos existente. El rollback consiste en
usar la imagen anterior y conservar los snapshots inmutables. PostgreSQL,
object storage y colas podrán añadirse mediante nuevos adaptadores sin cambiar
los conectores.
