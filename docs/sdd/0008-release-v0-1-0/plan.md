# Plan de implementación

## Diseño

- `DES-001`: traducir el README con redacción técnica concisa, manteniendo secciones, tablas, Mermaid y JSON de ejemplo; los documentos internos permanecen en español y se indica en el README.
- `DES-002`: agregar el badge de CI como única insignia, sin coverage, versión ni Docker.
- `DES-003`: crear la release con `gh release create` contra el SHA de `main`, con notas limitadas a capacidades existentes.

## Contratos

No cambian APIs, CLI, esquemas, configuración, layout de outputs ni workflows.

## Flujo de datos

Sin cambios: definición DIA y conector VTEX, transporte HTTP, extracción, normalización, controles de calidad, raw/normalized/current y manifest/logs.

## Fallos y recuperación

Si una validación o un check de CI falla, no se publica la release. La release es aditiva y puede corregirse con un nuevo tag sin reescribir historia.

## Pruebas

- Validador del repositorio y su self-test (enlaces y estructura SDD).
- pytest, Ruff check y Ruff format.
- Build Docker.
- Inventario de archivos versionados y comprobación de `.gitignore`.

## Despliegue

Pull request con checks y auto-merge según la política del repositorio; luego release desde `main`.
