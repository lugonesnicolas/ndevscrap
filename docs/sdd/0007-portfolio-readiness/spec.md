---
id: 0007-portfolio-readiness
title: Preparación de NDevScrap para portfolio profesional
status: done
owner: Nicolás Ezequiel Lugones
created: 2026-09-27
updated: 2026-09-27
approval: user-approved-2026-09-27
---

# Especificación

## Problema

NDevScrap ya contiene una implementación DIA/VTEX con contratos, controles de calidad y evidencia técnica, pero su portada concentra operación detallada y tarda en mostrar el alcance real a una persona que evalúa el repositorio.

## Objetivos

- Comunicar el propósito, la arquitectura y la implementación DIA/VTEX en una lectura breve.
- Conservar la documentación operativa, trasladándola a una guía enlazada.
- Añadir evidencia visual y ejemplos sanitizados que correspondan a los contratos implementados.
- Completar señales públicas de madurez del repositorio sin cambiar su arquitectura ni su comportamiento de adquisición.

## Alcance

Incluye README, guía de operaciones, licencia MIT, metadata de paquete, contribución y documentación SDD de este cambio. Excluye nuevos conectores, cambios funcionales, una ejecución externa contra DIA, infraestructura, releases, changelog y modificaciones de la cuenta de GitHub.

## Requisitos

- `REQ-001`: el README debe identificar NDevScrap, el problema que resuelve, DIA/VTEX como implementación actual, arquitectura, ejecución, validación y documentación en la primera lectura.
- `REQ-002`: la documentación operacional debe describir configuración, sesiones autorizadas, outputs, códigos de salida y Docker sin exponer secretos ni datos reales.
- `REQ-003`: los ejemplos de salida deben ser sanitizados y fieles a los modelos y CLI actuales.
- `REQ-004`: el repositorio debe incluir una licencia MIT y una descripción de paquete coherente con la narrativa pública.
- `REQ-005`: la iniciativa no debe alterar la autorización pendiente de DIA ni afirmar scheduler, cloud, Playwright o producción como capacidades implementadas.

## Restricciones

- Sigue ADR-0001, ADR-0002 y ADR-0003 sin cambios arquitectónicos.
- No se agregan badges cuyo estado no se pueda verificar, datos de output, HARs, tokens, cookies ni secretos.
- Las validaciones se ejecutan sin requests a DIA.

## Criterios de aceptación

- `AC-001`: README contiene diagrama Mermaid, capacidades verificables, DIA/VTEX, quick start, ejemplo sanitizado, calidad y enlaces válidos.
- `AC-002`: la guía de operaciones refleja la CLI, modelos, configuración, storage, seguridad de sesión y Docker implementados.
- `AC-003`: LICENSE contiene el texto MIT y `pyproject.toml` describe una plataforma modular de adquisición de datos para retail.
- `AC-004`: pytest, Ruff y ambos modos del validador pasan; Docker se construye si el entorno permite acceder al daemon.
- `AC-005`: el escaneo de archivos versionados no encuentra outputs, HARs ni material secreto accidental.
