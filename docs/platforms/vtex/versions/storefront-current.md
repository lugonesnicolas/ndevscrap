---
platform: vtex
version: storefront-current
status: active
created: 2026-09-23
updated: 2026-09-25
last_verified: 2026-09-25
---

# API: VTEX Storefront, versión actual por confirmar

## Estado y vigencia

- Estado: `active` para catálogo público.
- Última verificación: `2026-09-23`.
- Representa Intelligent Search v1, Catalog System y el flujo ClubDIA observado
  en la cuenta VTEX `diaio`.

## Endpoints

- `GET /api/intelligent-search/v1/product-search/{facets}`: catálogo paginado;
  acepta `page`, `count`, `locale`, `sc` y `zip-code`.
- `GET /api/catalog_system/pub/category/tree/3`: árbol usado para particionar el
  catálogo sin superar el límite de búsqueda.
- `GET /_v/private/club-dia/_v1/token-by-user`: obtiene un token ClubDIA efímero
  a partir de una sesión VTEX autorizada.
- `GET /_v/private/club-dia/_v1/cupons`: lista cupones personalizados usando
  `clubdia-auth-header` y `order-form-id`; la grafía `cupons` es la observada en
  el storefront.
- No se documentarán endpoints como confirmados a partir de patrones supuestos;
  cada uno requiere captura autorizada y fuente fechada.

## Paginación

- Intelligent Search informa `recordsFiltered` y metadata `pagination`. La
  verificación observó un máximo de 50 páginas y page size de hasta 50; por eso
  la extracción completa se divide por categorías y valida cada partición.
- El checkpoint recomendado conservará endpoint lógico, parámetros no secretos,
  página o cursor y hash de la última respuesta confirmada.

## Errores y reintentos

- `429`, timeouts y `5xx` recuperables usarán reintentos acotados y
  `Retry-After` cuando esté presente.
- `401` y `403` de ClubDIA se clasificarán como sesión vencida o autorización
  insuficiente y no se reintentarán sin renovar la sesión.
- La suite incluye fixtures sanitizadas del contrato real de cupones; ningún
  token, cookie, identidad ni respuesta autenticada completa se versiona.

## Mapeo al contrato

- Producto y SKU mapearán identidades, GTIN, nombre, marca, categorías, URL,
  imágenes, seller, disponibilidad, lista, venta, promoción y procedencia.
- Los importes se normalizarán como `Decimal` en ARS y se serializarán como
  cadenas.
- ClubDIA proyecta `id`, descripción, líneas de condiciones, tipo, vigencia,
  categoría y estado. Totales de compra/ahorro, token, cuenta y perfil se
  descartan.

## Diferencias y compatibilidad

- Legacy Search también está disponible, pero la implementación elige
  Intelligent Search v1 porque recibe explícitamente `zip-code` y `sc`.
- Un cambio de endpoint no debe modificar el esquema normalizado; un cambio
  incompatible del esquema requiere actualizar el SDD y versionar el contrato.

## Fuentes

- [VTEX Catalog API](https://developers.vtex.com/docs/api-reference/catalog-api),
  consultada el 2026-09-23.
- [VTEX Legacy Search API](https://developers.vtex.com/docs/api-reference/search-api),
  consultada el 2026-09-23.
- [DIA Online](https://diaonline.supermercadosdia.com.ar/), objetivo verificado
  mediante tráfico autorizado y endpoints públicos el 2026-09-25.

## Hallazgos pendientes

- Confirmar límites formales y contacto operativo de DIA.
- Medir la expiración efectiva de la sesión en operación diaria.
