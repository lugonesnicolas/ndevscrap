# Catálogo de plataformas

Este catálogo conserva conocimiento reutilizable obtenido al explorar APIs de
plataformas. Complementa las iniciativas SDD: la ficha describe la plataforma y
sus versiones; cada iniciativa documenta la tienda, configuración y decisiones
propias del conector.

## Cuándo crear o actualizar una ficha

Inicie una ficha durante el descubrimiento de una API, dentro de una iniciativa
SDD en `draft`. Antes de reutilizar una plataforma en otra iniciativa, revise su
fecha de verificación y sus versiones activas. Actualícela cuando la
documentación oficial cambie o cuando una prueba operativa detecte un cambio.

No cree una ficha para una particularidad exclusiva de una tienda. Regístrela en
el SDD o en su configuración externa.

## Estructura

```text
docs/platforms/
  <plataforma>/
    README.md
    versions/
      <version>.md
```

Copie [la plantilla de ficha](templates/platform.md) como
`<plataforma>/README.md` y [la de versión](templates/version.md) como
`<plataforma>/versions/<version>.md`. Use slugs kebab-case en minúsculas. El
directorio `versions/` puede estar vacío mientras la API siga en exploración.

## Evidencia y estados

Una ficha y sus anexos usan `draft`, `active` o `retired`:

- `draft`: exploración en curso. Puede usar `last_verified: pending` y debe
  dejar las hipótesis en `## Hallazgos pendientes`.
- `active`: información disponible para reutilizar. `last_verified` debe tener
  una fecha ISO y los hechos deben enlazar una fuente en `## Fuentes`.
- `retired`: versión o plataforma que se conserva como historial. Mantenga la
  última fecha verificada, su motivo de retiro y los enlaces al reemplazo cuando
  exista.

Un hecho confirmado indica fuente y fecha de observación o verificación. Los
campos aún no confirmados se escriben como pendientes; nunca como una capacidad
confirmada. No incluya secretos, tokens, respuestas sin sanitizar ni datos de
una tienda.

## Mantenimiento de versiones

La ficha principal resume capacidades compartidas y enlaza cada versión activa.
Cada anexo registra endpoints, paginación, errores, mapeos y diferencias de su
versión. Cuando una versión cambie, cree o actualice su anexo y marque el
anterior como `retired` si deja de estar soportado. Actualice `updated` al editar
el documento y `last_verified` después de comprobar la API o su documentación.

Los enlaces a iniciativas SDD permiten reconstruir por qué y dónde se usó cada
plataforma. Un cambio transversal de contrato, seguridad o arquitectura se
registra además mediante ADR.
