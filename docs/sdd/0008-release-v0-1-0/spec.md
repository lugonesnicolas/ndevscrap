---
id: 0008-release-v0-1-0
title: Cierre de portfolio y release v0.1.0
status: done
owner: Nicolás Ezequiel Lugones
created: 2026-09-28
updated: 2026-09-28
approval: user-approved-2026-09-28
---

# Especificación

## Problema

El README principal está en español y no expone el estado de CI; el repositorio será el proyecto principal de portfolio para una audiencia internacional y todavía no tiene una release pública.

## Objetivos

- Presentar el README principal en inglés técnico, sin cambiar contratos ni capacidades.
- Mostrar un badge de CI respaldado por `.github/workflows/ci.yml`.
- Publicar la release `v0.1.0` desde `main` cuando la validación sea correcta.

## Alcance

Incluye `README.md`, esta iniciativa, validación y la release. Excluye código funcional, workflows, nuevos conectores, traducción de `docs/`, ADRs o SDD, y cualquier request real contra DIA.

## Requisitos

- `REQ-001`: el README debe estar completamente en inglés y conservar la estructura, el diagrama Mermaid, los comandos y los ejemplos sanitizados vigentes.
- `REQ-002`: el README debe incluir únicamente el badge de CI del workflow real.
- `REQ-003`: todos los enlaces relativos del README deben resolver a archivos existentes.
- `REQ-004`: la release `v0.1.0` debe coincidir con la versión de `pyproject.toml` y crearse desde el commit integrado de `main` con CI verde.

## Restricciones

- Sigue ADR-0001 a ADR-0003 sin cambios.
- No se afirman capacidades no implementadas ni métricas no verificadas en esta ejecución.
- No se versionan secretos, HARs, sesiones ni outputs.
- No se reescribe historia ni se hace force push.

## Criterios de aceptación

- `AC-001`: README en inglés con la estructura conceptual vigente y DIA/VTEX como implementación actual.
- `AC-002`: badge de CI presente y apuntando a `ci.yml`.
- `AC-003`: enlaces relativos válidos y validador del repositorio correcto.
- `AC-004`: pytest, Ruff, validador, self-test y build Docker pasan.
- `AC-005`: inventario de archivos versionados sin material sensible.
- `AC-006`: release `v0.1.0` publicada con las notas acordadas.
