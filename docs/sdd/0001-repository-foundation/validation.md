# Validación

## Resultado

La iniciativa cumple los criterios y queda lista para cerrar.

## Evidencia

- `python scripts/validate_repository.py` valida documentos, metadata, secciones
  y enlaces locales.
- `python scripts/validate_repository.py --self-test` crea un paquete temporal
  incompleto y confirma que se rechaza con errores accionables.
- `.github/workflows/quality.yml` ejecuta el validador y omite con un mensaje
  explícito los pasos Python cuando falta `pyproject.toml`.

## Criterios de aceptación

- `AC-001`: satisfecho; README enlaza las fuentes canónicas y el ejemplo.
- `AC-002`: satisfecho; arquitectura, ADR-0001 y ADR-0002 registran las
  decisiones.
- `AC-003`: satisfecho; el paquete `0001` usa y supera las reglas comunes.
- `AC-004`: satisfecho; el self-test exige y verifica un fallo accionable.
- `AC-005`: satisfecho; CI detecta `pyproject.toml` antes de instalar o ejecutar
  herramientas Python.

## Desviaciones

No hubo desviaciones respecto del plan aprobado.
