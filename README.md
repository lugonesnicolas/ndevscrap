# NDevScrap

NDevScrap es la base para construir y operar scrapers Python para múltiples
tiendas y plataformas con contratos consistentes. El proyecto prioriza APIs y
HTML estático, reserva el navegador para los casos que realmente lo necesitan y
mantiene separadas la extracción, la ejecución y la persistencia.

El repositorio está en su etapa de fundación documental. Aún no contiene el
primer scraper ni el runtime Python; esas piezas se incorporarán mediante el
ciclo SDD definido en este repositorio.

## Principios

- Un monolito modular es el punto de partida; los límites internos deben permitir
  separar componentes cuando el volumen lo justifique.
- Un conector implementa un contrato estable y reutiliza componentes mediante
  composición.
- Las variaciones se modelan como plataforma, configuración de tienda y overrides
  específicos, en ese orden.
- La estrategia de acceso es API, luego HTML estático y finalmente Playwright.
- Toda ejecución debe ser observable, reintentable e idempotente.
- Los datos conservan su origen y avanzan por capas raw, normalized y current.
- No se eluden controles de acceso ni medidas antiabuso.

La descripción normativa y los trade-offs están en la
[guía de arquitectura](docs/architecture.md). Las decisiones duraderas se
registran como [ADR](docs/adr/README.md).

## Cómo se trabaja

Todo scraper o cambio funcional comienza con una iniciativa SDD. Antes de
programar deben estar aprobados sus requisitos y su plan; al finalizar, la
evidencia se registra junto al cambio.

1. Leer la [guía de contribución](CONTRIBUTING.md).
2. Crear la iniciativa desde las [plantillas SDD](docs/sdd/README.md).
3. Aprobar `spec.md` y `plan.md`.
4. Implementar las tareas manteniendo trazabilidad con los requisitos.
5. Ejecutar las validaciones y completar `validation.md`.
6. Abrir un pull request usando la plantilla del repositorio.

El paquete [0001-repository-foundation](docs/sdd/0001-repository-foundation/spec.md)
muestra el proceso completo aplicado a esta base documental.

## Estructura objetivo

```text
src/                 CLI, contratos compartidos y conectores
tests/               pruebas y fixtures HTML/JSON locales
docs/                arquitectura, ADR e iniciativas SDD
scripts/             herramientas de desarrollo sin lógica de scraping
output/              resultados locales no versionados
Dockerfile           imagen portable para ejecución headless
```

Las rutas de código son objetivo de la siguiente etapa y no existen todavía.

## Inicio rápido futuro

Cuando el primer MVP incorpore `pyproject.toml`, `.env.example` y la CLI, el
flujo esperado será:

```bash
uv sync
cp .env.example .env
uv run ndevscrap run <connector> --output output/result.jsonl
```

La misma interfaz se ejecutará en local y en contenedores. Los adaptadores de un
proveedor cloud vivirán fuera de los conectores.

## Validar este repositorio

La documentación y los paquetes SDD se validan sin instalar dependencias:

```bash
python scripts/validate_repository.py
python scripts/validate_repository.py --self-test
```

GitHub Actions ejecuta estas comprobaciones en cada push y pull request. Cuando
exista `pyproject.toml`, ejecutará también `pytest` y Ruff.

## Operación responsable

Las credenciales y los resultados sensibles nunca se versionan. Cada iniciativa
de scraper debe evaluar términos del sitio, `robots.txt` cuando corresponda,
timeouts, límites de frecuencia, retención y tratamiento de datos antes de ser
aprobada.
