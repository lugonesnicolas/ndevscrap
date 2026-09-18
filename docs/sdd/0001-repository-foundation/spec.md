---
id: 0001-repository-foundation
title: Base documental y ciclo SDD
status: done
owner: maintainers
created: 2026-09-18
updated: 2026-09-18
approval: user-approved-2026-09-18
---

# Especificación

## Problema

El repositorio sólo contenía una descripción inicial y no definía contratos,
decisiones arquitectónicas, workflow de contribución ni un proceso verificable
para desarrollar scrapers de forma consistente.

## Objetivos

- Formalizar las bases arquitectónicas para múltiples tiendas y plataformas.
- Definir un ciclo SDD pragmático y trazable.
- Proveer plantillas, un ejemplo completo y validación automática.
- Preparar el repositorio para diseñar el primer scraper por separado.

## Alcance

Incluye documentación normativa, ADR, instrucciones para agentes, plantilla de
pull request y CI documental. Excluye runtime Python, dependencias, Docker, CLI,
infraestructura productiva y el primer scraper.

## Requisitos

- `REQ-001`: el repositorio debe documentar la arquitectura acordada y sus
  decisiones duraderas.
- `REQ-002`: toda iniciativa estándar debe registrar spec, plan, tareas y
  validación mediante estados definidos.
- `REQ-003`: colaboradores y agentes deben encontrar un workflow inequívoco.
- `REQ-004`: CI debe validar estructura SDD, enlaces y formato básico sin
  dependencias externas.
- `REQ-005`: la validación documental debe convivir con la CI Python sin
  duplicar la ejecución de pytest y Ruff.

## Restricciones

- La documentación normativa se escribe en español.
- Los nombres técnicos y estados permanecen en inglés.
- La validación no depende de sitios ni servicios externos.
- Esta iniciativa no agrega código de scraping ni dependencias de producto.

## Criterios de aceptación

- `AC-001`: README enlaza arquitectura, contribución, SDD y el ejemplo.
- `AC-002`: arquitectura y ADR formalizan conectores modulares y API-first.
- `AC-003`: el paquete SDD de referencia supera el mismo validador que futuros
  paquetes.
- `AC-004`: un paquete incompleto falla con un mensaje accionable.
- `AC-005`: workflows separados validan documentación y proyecto Python sin
  ejecutar dos veces pytest o Ruff.
