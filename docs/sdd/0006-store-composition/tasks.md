# Tareas

## Tareas

- [x] `TASK-001` Escribir las pruebas nuevas y adaptar las de 0005 a las nuevas
  firmas, sin debilitar aserciones, y registrar cuáles fallan con el código de
  la base (`AC-001` a `AC-011`).
- [x] `TASK-002` Endurecer `RequestsTransport` y agregar `stats()` y
  `build_transport` para `REQ-007` y `REQ-008` según `DES-011` a `DES-013`.
- [x] `TASK-003` Implementar `HttpSettings`, `RunSettings` y el hash de
  configuración para `REQ-006` y `REQ-008` según `DES-011` y `DES-014`.
- [x] `TASK-004` Generalizar los contratos y `FileSnapshotStore` por componente
  para `REQ-001` según `DES-002` y `DES-003`.
- [x] `TASK-005` Implementar `QualityGate`, `QualityPolicy` y el runner genérico
  en streaming con clasificación de errores por componente para `REQ-002`,
  `REQ-003` y `REQ-005` según `DES-004` a `DES-007`.
- [x] `TASK-006` Implementar `VtexSettings`, el paquete `stores/` con el
  registro y la definición DIA, y mover la extracción del HAR para `REQ-003`,
  `REQ-004` y `REQ-010` según `DES-008` a `DES-010`.
- [x] `TASK-007` Implementar el manifest v2, `observability.py` y la CLI sobre
  el registro para `REQ-008`, `REQ-009` y `REQ-012` según `DES-014` y
  `DES-015`.
- [x] `TASK-008` Actualizar el script de sesión, `.gitignore`, `.dockerignore`,
  `.env.example`, `README.md`, el ADR-0003 y su índice para `REQ-006`,
  `REQ-010` y `REQ-011`, y registrar en
  `0004-dia-vtex-connector/validation.md` las brechas que cierra 0006.
- [ ] `TASK-009` Ejecutar pytest, Ruff, validadores y mutaciones en Windows,
  obtener las revisiones QA de contrato y de seguridad, incorporar hallazgos y
  registrar la evidencia de `AC-001` a `AC-012`.
