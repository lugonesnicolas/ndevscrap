# Contribuir a NDevScrap

Este documento describe el flujo cotidiano. La arquitectura normativa está en
[docs/architecture.md](docs/architecture.md) y el proceso de especificación en
[docs/sdd/README.md](docs/sdd/README.md).

## 1. Preparar el entorno

Se requiere Git, Python 3.12 y `uv`. El proyecto y sus dependencias de desarrollo
se definen en `pyproject.toml`.

Antes de comenzar:

```bash
uv sync --all-groups
python scripts/validate_repository.py
git status --short
```

No incluya credenciales, respuestas reales sensibles ni contenido de `output/`.

## 2. Abrir una iniciativa SDD

Use un identificador correlativo de cuatro dígitos y un slug en kebab-case:
`docs/sdd/<id>-<slug>/`. Copie las plantillas correspondientes y complete
primero `spec.md` y `plan.md`.

Un cambio funcional o un scraper usa el paquete estándar de cuatro archivos. Un
ajuste trivial y localizado puede usar `compact.md` sólo si no modifica
contratos, arquitectura, datos, seguridad ni operación. Consulte los criterios
detallados en la [guía SDD](docs/sdd/README.md).

No comience la implementación hasta que la iniciativa tenga estado `approved`.

## 3. Implementar

- Cambie el estado a `in-progress` y ejecute las tareas en orden.
- Mantenga cada tarea vinculada con un requisito o decisión del plan.
- Prefiera componentes pequeños y composición sobre jerarquías de herencia.
- No introduzca Playwright si la información puede obtenerse mediante API o HTML.
- Agregue fixtures locales y pruebas; la suite normal no depende de tiendas reales.
- Si la implementación se aparta del plan, actualice y vuelva a revisar el SDD
  antes de continuar.
- Cree un ADR únicamente para una decisión transversal y duradera.

## 4. Validar

Cambie el estado de la iniciativa a `validation`, ejecute las comprobaciones y
registre resultados reproducibles en `validation.md`.

```bash
python scripts/validate_repository.py
python scripts/validate_repository.py --self-test
```

Ejecute además las comprobaciones del proyecto Python:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Los smoke tests contra sitios externos son controles operativos separados; no
forman parte de la suite determinista habitual.

## 5. Cerrar y presentar el cambio

- Complete la evidencia para cada criterio de aceptación.
- Documente desviaciones, incluso cuando no impidan el cierre.
- Actualice arquitectura o ADR si cambió una decisión transversal.
- Cambie el estado a `done` sólo cuando todas las tareas y validaciones estén
  completas.
- Abra el pull request, enlace la iniciativa y complete todo el checklist.

Los commits deben ser pequeños y describir su intención. No se permite force
push como parte del workflow normal del repositorio.
