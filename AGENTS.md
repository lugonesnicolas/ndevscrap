# Instrucciones para agentes

Estas reglas aplican a todo el repositorio.

## Antes de modificar

1. Lea `README.md`, `docs/architecture.md` y los ADR aceptados.
2. Lea `docs/sdd/README.md` y localice la iniciativa activa.
3. No implemente un scraper ni un cambio funcional si su `spec.md` y `plan.md`
   no están completos y la iniciativa no tiene estado `approved` o
   `in-progress`.
4. Si no existe una iniciativa adecuada, créela y deténgase en la aprobación
   antes de escribir código de producto.

## Durante el trabajo

- Mantenga el alcance limitado a la iniciativa y sus tareas.
- Conserve trazabilidad entre requisitos, tareas, pruebas y validación.
- Actualice el SDD antes de introducir una desviación relevante.
- Respete la prioridad API, HTML estático y Playwright.
- Separe extracción, ejecución, configuración y almacenamiento.
- No agregue secretos, resultados sensibles ni dependencias de sitios externos a
  la suite determinista.
- No revierta cambios ajenos sin autorización.

## Al finalizar

- Ejecute `python scripts/validate_repository.py` y las comprobaciones Python
  disponibles.
- Complete `validation.md` con evidencia reproducible.
- Cambie el estado a `done` sólo si todos los criterios están satisfechos.
- Si sincroniza o actualiza un fork, use operaciones seguras y nunca force push.
