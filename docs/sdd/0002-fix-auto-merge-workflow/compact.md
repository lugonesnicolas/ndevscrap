---
id: 0002-fix-auto-merge-workflow
title: Corregir resolución del repositorio en auto-merge
status: done
owner: maintainers
created: 2026-09-18
updated: 2026-09-18
approval: user-requested-2026-09-18
---

# Cambio SDD compacto

## Problema

El workflow `pull_request_target` ejecuta GitHub CLI sin checkout y sin indicar
el repositorio. `gh pr view` y `gh pr merge` intentan descubrirlo mediante
`.git`, que no existe en el runner, y terminan con código 1 antes de habilitar
auto-merge.

## Cambio

Definir `GH_REPO` desde `github.repository` y pasar `--repo "$GH_REPO"` a ambas
llamadas de GitHub CLI. Se mantiene el workflow sin checkout para no ejecutar ni
leer contenido de una rama no confiable bajo `pull_request_target`.

## Criterios de aceptación

- `AC-001`: `gh pr view` recibe explícitamente el repositorio.
- `AC-002`: `gh pr merge` recibe explícitamente el mismo repositorio.
- `AC-003`: el workflow no agrega checkout de la rama del pull request.
- `AC-004`: validación documental, pytest y Ruff permanecen verdes.

## Tareas

- [x] `TASK-001`: identificar el fallo en el log del run `35402128691`.
- [x] `TASK-002`: agregar `GH_REPO` y `--repo` a las llamadas afectadas.
- [x] `TASK-003`: validar estructura, pruebas y formato del repositorio.

## Validación

El log remoto confirma que la ausencia de contexto Git era la causa. La
configuración actual pasa el repositorio explícitamente, conserva el modelo de
seguridad de `pull_request_target` y supera el validador del repositorio, pytest,
Ruff lint y Ruff format. No hubo desviaciones.
