---
id: vtex
status: active
created: 2026-09-23
updated: 2026-09-25
last_verified: 2026-09-25
---

# Plataforma: VTEX

## Estado y vigencia

- Estado: `active`.
- Última verificación: `2026-09-23`.
- Alcance: capacidades de catálogo y búsqueda relevantes para conectores de
  tiendas VTEX y la configuración confirmada de DIA Online para CP `1806`.

## Acceso autorizado

- VTEX documenta APIs de catálogo, búsqueda y checkout con endpoints públicos y
  privados; cada endpoint debe clasificarse por documentación y por la
  autorización de la tienda antes de utilizarse.
- Las APIs privadas requieren credenciales VTEX con permisos mínimos. La
  iniciativa DIA no almacenará AppKey, AppToken, cookies ni sesiones en Git.
- El uso de una sesión de comprador para ClubDIA se limita a endpoints de sólo
  lectura autorizados y no forma parte del comportamiento reutilizable de VTEX.
  DIA obtiene un token efímero con la sesión VTEX y lo intercambia por cupones;
  ninguno de ambos secretos se conserva en snapshots.

## Capacidades

- La documentación oficial confirma entidades de producto, SKU, categoría,
  marca, especificaciones y variantes.
- Legacy Search permite buscar y paginar productos y consultar ofertas. DIA
  Online expone además Intelligent Search v1 y el árbol público de categorías;
  la búsqueda acepta código postal y canal de venta.
- DIA contextualiza Intelligent Search mediante `zip-code=1806` y canal de
  venta `sc=1`. ClubDIA requiere además el `order-form-id` efímero de la sesión,
  sin leer ni persistir contenido del carrito.

## Límites y operación

- Los límites publicados varían por API y cuenta; deben confirmarse para cada
  integración. El conector DIA comenzará con una solicitud por segundo,
  concurrencia uno y hasta tres reintentos configurables.
- Se deben respetar `Retry-After`, clasificar `429`, `5xx`, autenticación y
  cambios de esquema, y evitar consultas por SKU cuando una respuesta paginada
  ya contiene los datos necesarios.
- Deben observarse cantidad de páginas, productos, SKU, rechazos, latencia,
  reintentos, códigos HTTP y antigüedad del último snapshot válido.

## Versiones de API

- [Storefront actual en descubrimiento](versions/storefront-current.md).

## Iniciativas SDD relacionadas

- [0004-dia-vtex-connector](../../sdd/0004-dia-vtex-connector/spec.md).

## Mantenimiento

- Revisar cuando VTEX retire un endpoint de búsqueda, cambie el contrato de
  ofertas o una tienda migre entre Legacy Search e Intelligent Search.
- Responsable: maintainers.
- El 2026-09-25 se verificaron la cuenta `diaio`, Intelligent Search v1, el
  árbol de categorías, el límite observado de 50 páginas por partición y el
  flujo ClubDIA usado por el storefront.

## Fuentes

- [VTEX Catalog API](https://developers.vtex.com/docs/api-reference/catalog-api),
  consultada el 2026-09-23 para entidades y autenticación.
- [VTEX Legacy Search API](https://developers.vtex.com/docs/api-reference/search-api),
  consultada el 2026-09-23 para búsqueda, paginación y ofertas.
- [VTEX Checkout](https://developers.vtex.com/docs/guides/vtexjs-for-checkout),
  consultada el 2026-09-23 para contexto logístico por código postal.
- [DIA Online](https://diaonline.supermercadosdia.com.ar/), consultada el
  2026-09-25 mediante tráfico autorizado y consultas limitadas a Intelligent
  Search, árbol de categorías y cupones ClubDIA de sólo lectura.

## Hallazgos pendientes

- Confirmar límites autorizados y datos de contacto operativo.
- Registrar la vigencia práctica de la sesión mediante ejecuciones programadas.
