# Ciclo Spec-Driven Development

SDD es el registro ejecutable de intención, diseño, trabajo y evidencia. Se usa
para que una decisión pueda revisarse antes de programar y verificarse al cerrar.

## Elegir el formato

Use un paquete estándar para scrapers, funcionalidades, refactors relevantes,
cambios operativos y cualquier modificación de contratos, datos, seguridad o
arquitectura. Cree `docs/sdd/<id>-<slug>/` copiando:

- [spec.md](templates/spec.md)
- [plan.md](templates/plan.md)
- [tasks.md](templates/tasks.md)
- [validation.md](templates/validation.md)

Use [compact.md](templates/compact.md) únicamente para correcciones triviales,
localizadas y reversibles que no cambien ninguno de esos aspectos. Un directorio
compacto contiene sólo `compact.md`.

El identificador tiene cuatro dígitos correlativos y el slug usa kebab-case. La
metadata de `spec.md` o `compact.md` es la fuente canónica del estado.

## Estados y transiciones

```text
draft -> approved -> in-progress -> validation -> done
```

- `draft`: requisitos o diseño todavía cambian; no se implementa.
- `approved`: requisitos y plan fueron revisados; puede comenzar el trabajo.
- `in-progress`: existen cambios de implementación en curso.
- `validation`: terminó la implementación y se reúne evidencia.
- `done`: tareas completas, criterios satisfechos y desviaciones registradas.

Si cambia materialmente el alcance o el diseño, la iniciativa vuelve a `draft`
hasta una nueva aprobación. La aprobación se registra en `spec.md`, indicando
persona o mecanismo y fecha.

## Trazabilidad

- Los requisitos se identifican como `REQ-001`, `REQ-002`, etc.
- Los criterios de aceptación se identifican como `AC-001`, `AC-002`, etc.
- Las decisiones del plan se identifican como `DES-001`, `DES-002`, etc.
- Las tareas mencionan los identificadores que implementan.
- `validation.md` aporta evidencia por cada criterio de aceptación.

Un pull request enlaza la iniciativa, resume las desviaciones y no marca el SDD
como `done` hasta que la validación sea reproducible.

## Gates

1. **Aprobación:** `spec.md` y `plan.md` completos antes de implementar.
2. **Implementación:** tareas trazables y desviaciones actualizadas antes de
   cambiar el comportamiento acordado.
3. **Validación:** evidencia por criterio, pruebas y documentación actualizada.
4. **Cierre:** estado `done` y pull request con checklist completo.

Un ADR se agrega sólo cuando la iniciativa introduce o modifica una decisión
arquitectónica transversal. El ADR enlaza el SDD y el plan enlaza el ADR.

## Validación automática

Ejecute:

```bash
python scripts/validate_repository.py
```

El validador comprueba nombres, archivos, metadata, estados, secciones
obligatorias, formato básico y enlaces locales. `--self-test` prueba que un
paquete incompleto sea rechazado con un error accionable.

## Referencia

La iniciativa [0001-repository-foundation](0001-repository-foundation/spec.md)
documenta la creación de estas bases y sirve como ejemplo terminado.
