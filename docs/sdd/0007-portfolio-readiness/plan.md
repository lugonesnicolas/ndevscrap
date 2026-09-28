# Plan de implementación

## Diseño

- `DES-001`: usar el README como portada de lectura progresiva; mantener sólo el quick start y desplazar operación detallada a `docs/operations.md`.
- `DES-002`: usar Mermaid versionado en Markdown para el flujo real DIA/VTEX, sin generar assets binarios.
- `DES-003`: representar salida sólo con valores ficticios y campos de `ProductSnapshot` y de la línea final de la CLI.
- `DES-004`: usar MIT, elegida por el propietario, con la atribución de 2026.

## Contratos

No cambian APIs, esquemas, CLI, configuración ni layout de outputs. La guía documenta los contratos existentes: `ndevscrap run dia`, `ProductSnapshot`, `RunManifest` v2 y las variables `NDEVSCRAP_*`.

## Flujo de datos

El diagrama y la documentación presentan el flujo vigente: definición DIA y conector VTEX, transporte HTTP, extracción, normalización, controles de calidad, raw/normalized/current y manifest/logs. ClubDIA permanece como componente opcional y sensible.

## Fallos y recuperación

La documentación conserva la semántica existente: configuración inválida devuelve `1` antes de escribir, errores del componente opcional producen éxito parcial cuando el catálogo publica, y los fallos transitorios pueden conservar staging para reanudar. No cambia el código de recuperación.

## Pruebas

- Verificar enlaces y estructura SDD con el validador del repositorio.
- Ejecutar pytest y Ruff contra el árbol actualizado.
- Contrastar ejemplos con `models.py`, `cli.py`, `.env.example`, `storage.py` y Dockerfile.
- Buscar indicadores de secretos, HARs y outputs entre archivos versionados.

## Despliegue

No requiere migración ni activación. La metadata de GitHub y LinkedIn se entrega como recomendación para que el propietario la aplique fuera del repositorio.
