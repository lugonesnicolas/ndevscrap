---
id: 0003-platform-documentation
title: Estándar de documentación de plataformas
status: validation
owner: maintainers
created: 2026-09-20
updated: 2026-09-20
approval: user-approved-2026-09-20
---

# Especificación

## Problema

El repositorio no tiene un lugar ni un formato común para conservar el
conocimiento reutilizable obtenido durante la exploración de APIs. Cada nuevo
conector podría repetir la investigación o documentarla de forma inconsistente.

## Objetivos

- Crear un catálogo versionable y reutilizable de plataformas.
- Diferenciar evidencia confirmada de hallazgos pendientes.
- Mantener el historial de APIs que evolucionan sin mezclar sus versiones.
- Detectar automáticamente fichas incompletas con reglas estructurales básicas.

## Alcance

Incluye documentación del catálogo, plantillas, enlaces al workflow y validación
de estructura. Excluye documentar una API concreta, implementar conectores,
consultar servicios externos y modificar contratos de datos.

## Requisitos

- `REQ-001`: el repositorio debe definir una ficha reutilizable por plataforma
  y un anexo por versión de API.
- `REQ-002`: las fichas deben registrar acceso autorizado, capacidades, límites,
  fuentes, SDD relacionados y fecha de última verificación sin secretos.
- `REQ-003`: las fichas deben distinguir estados, evidencia confirmada y
  hallazgos pendientes durante la exploración.
- `REQ-004`: el workflow debe indicar cuándo crear, revisar y retirar fichas y
  versiones ante cambios de plataforma.
- `REQ-005`: el validador debe detectar una estructura incompleta sin evaluar
  la veracidad de la API.

## Restricciones

- La documentación normativa se escribe en español y los slugs en kebab-case.
- El catálogo no contiene credenciales, respuestas reales ni datos de tiendas.
- Las reglas automáticas validan estructura y metadata; la evidencia se revisa
  por personas.
- Esta iniciativa no requiere ADR porque no modifica decisiones transversales.

## Criterios de aceptación

- `AC-001`: existen guía y plantillas para ficha de plataforma y anexo de
  versión, con secciones requeridas para `REQ-001` y `REQ-002`.
- `AC-002`: una ficha `draft` puede declarar información pendiente sin
  presentarla como confirmada, para `REQ-003`.
- `AC-003`: la guía define actualización, verificación y retiro de versiones,
  para `REQ-004`.
- `AC-004`: una ficha y un anexo válidos superan el validador; una estructura
  incompleta falla con un mensaje accionable, para `REQ-005`.
- `AC-005`: README, contribución y SDD enlazan el catálogo y explican su uso.
