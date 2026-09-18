# ADR-0002: Estrategia API-first y aislamiento del navegador

- Estado: `accepted`
- Fecha: 2026-09-18
- Iniciativa: [0001-repository-foundation](../sdd/0001-repository-foundation/spec.md)

## Contexto

Las tiendas exponen datos mediante mecanismos con costos y estabilidad muy
distintos. Ejecutar siempre un navegador aumenta consumo, latencia y superficie
de fallos, pero algunas experiencias dinámicas no ofrecen una alternativa
estática suficiente.

## Decisión

Elegir adquisición en el orden API autorizada, HTML estático y Playwright
headless. El mecanismo será un adaptador detrás del contrato del conector.

Los trabajos que requieren navegador deberán identificarse explícitamente y
poder ejecutarse en workers y colas separados de los trabajos HTTP. Local,
contenedor y cloud conservarán la misma interfaz pública.

## Consecuencias

- La mayoría de ejecuciones utiliza el mecanismo más simple y económico.
- Un conector puede cambiar su adaptador sin alterar su salida normalizada.
- El navegador puede escalar y fallar de manera independiente.
- Cada conector debe justificar y probar la necesidad de Playwright.
- Mantener varios adaptadores añade contratos internos que requieren pruebas.

## Alternativas descartadas

- Playwright para todas las fuentes: costo y fragilidad innecesarios.
- Prohibir navegadores: excluiría tiendas legítimamente dinámicas.
- Incorporar lógica de navegador directamente en cada parser: acopla adquisición
  y transformación.
