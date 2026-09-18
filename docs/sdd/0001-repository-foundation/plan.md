# Plan de implementación

## Diseño

- `DES-001`: separar fuentes canónicas para arquitectura, contribución y SDD,
  enlazándolas desde README para evitar duplicación.
- `DES-002`: usar paquetes estándar de cuatro archivos y una excepción compacta
  únicamente para cambios triviales.
- `DES-003`: implementar validación con la biblioteca estándar de Python para no
  agregar dependencias.
- `DES-004`: usar un único workflow de GitHub Actions con pasos Python
  condicionales a la existencia de `pyproject.toml`.

## Contratos

La metadata SDD usa front matter simple con `id`, `title`, `status`, `owner`,
`created`, `updated` y `approval`. Los estados válidos son `draft`, `approved`,
`in-progress`, `validation` y `done`. Los directorios usan cuatro dígitos y un
slug en kebab-case.

El contrato conceptual de conectores declara metadata, configuración tipada,
descubrimiento, extracción y normalización, sin crear todavía módulos Python.

## Flujo de datos

El validador recorre documentos Markdown y paquetes SDD, analiza metadata y
secciones, resuelve enlaces locales y acumula errores. Devuelve cero cuando el
repositorio es válido y un código distinto de cero con mensajes accionables en
caso contrario.

## Fallos y recuperación

La validación no modifica archivos. Todos los errores se informan en una única
ejecución para acelerar la corrección. El self-test usa un directorio temporal y
comprueba que un paquete incompleto sea rechazado.

## Pruebas

- Ejecutar el validador sobre el paquete `0001` para `REQ-002` y `AC-003`.
- Ejecutar `--self-test` para `REQ-004` y `AC-004`.
- Revisar todos los enlaces locales para `REQ-001`, `REQ-003` y `AC-001`.
- Inspeccionar la rama condicional de CI para `REQ-005` y `AC-005`.

## Despliegue

El cambio se activa al fusionar los documentos y el workflow en la rama
principal. No requiere migración ni rollback de datos. Revertir el commit restaura
el estado documental anterior.
