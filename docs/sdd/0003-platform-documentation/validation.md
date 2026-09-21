# Validación

## Resultado

La iniciativa cumple los criterios de aceptación y queda lista para cerrar.

## Evidencia

- `python scripts/validate_repository.py` — OK: documentos, enlaces y paquetes
  SDD válidos.
- `python scripts/validate_repository.py --self-test` — OK: valida una ficha y
  un anexo `draft` completos, y rechaza un SDD y una ficha incompletos con
  mensajes accionables.
- `.venv\Scripts\pytest.exe --basetemp .venv\pytest-tmp` — OK: 3 pruebas
  superadas con Python 3.12.14 y pytest 9.1.1. Se eligió una carpeta temporal
  local porque el sandbox no permite acceder al directorio temporal de pytest
  del usuario.
- `.venv\Scripts\ruff.exe check .` — OK: todas las comprobaciones superadas.
- `.venv\Scripts\ruff.exe format --check .` — OK: 30 archivos formateados.
- `git diff --check` — OK: sin errores de whitespace.

## Criterios de aceptación

- `AC-001`: satisfecho; existen guía y plantillas para ficha y versión.
- `AC-002`: satisfecho; las plantillas `draft` usan `last_verified: pending` y
  una sección explícita de hallazgos pendientes.
- `AC-003`: satisfecho; la guía define estados, verificación y retiro de
  versiones.
- `AC-004`: satisfecho; validador, self-test y pruebas pytest superados.
- `AC-005`: satisfecho; README, contribución y la guía SDD enlazan el catálogo.

## Desviaciones

No hubo desviaciones de diseño. La validación se ejecutó desde el entorno
virtual Python 3.12 existente porque `uv` no está disponible en `PATH`. Tras el
primer run de CI se corrigió el espaciado del bloque de imports marcado como
`I001` y se aplicó el formato requerido al validador.
