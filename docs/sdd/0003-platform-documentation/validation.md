# Validación

## Resultado

La implementación y la validación documental están completas. La iniciativa se
mantiene en `validation` hasta ejecutar pytest y Ruff en un entorno con las
dependencias de desarrollo disponibles.

## Evidencia

- `python scripts/validate_repository.py` — OK: documentos, enlaces y paquetes
  SDD válidos.
- `python scripts/validate_repository.py --self-test` — OK: valida una ficha y
  un anexo `draft` completos, y rechaza un SDD y una ficha incompletos con
  mensajes accionables.
- `python -m py_compile scripts/validate_repository.py
  tests/test_validate_repository.py` — OK.
- `python -m pytest`, `python -m ruff check .` y `python -m ruff format --check
  .` — no ejecutados: el intérprete disponible es Python 3.9 sin los módulos
  `pytest` ni `ruff`; `uv` tampoco está instalado en este entorno.

## Criterios de aceptación

- `AC-001`: satisfecho; existen guía y plantillas para ficha y versión.
- `AC-002`: satisfecho; las plantillas `draft` usan `last_verified: pending` y
  una sección explícita de hallazgos pendientes.
- `AC-003`: satisfecho; la guía define estados, verificación y retiro de
  versiones.
- `AC-004`: satisfecho por el validador y su self-test; la prueba pytest añadida
  queda pendiente de un entorno con dependencias de desarrollo.
- `AC-005`: satisfecho; README, contribución y la guía SDD enlazan el catálogo.

## Desviaciones

No hubo desviaciones respecto del plan. La falta de `uv`, pytest y Ruff impide
cerrar la iniciativa con todas las comprobaciones requeridas por el repositorio.
