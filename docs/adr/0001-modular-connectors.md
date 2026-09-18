# ADR-0001: Monolito modular y modelo de conectores

- Estado: `accepted`
- Fecha: 2026-09-18
- Iniciativa: [0001-repository-foundation](../sdd/0001-repository-foundation/spec.md)

## Contexto

La plataforma debe admitir muchas tiendas sin duplicar adquisición,
normalización y operación. Separar servicios desde el inicio añadiría costo sin
datos de escala, mientras que un scraper independiente por dominio dificultaría
el mantenimiento.

## Decisión

Comenzar con un monolito modular y un contrato estable de conectores. Reutilizar
por composición clientes, autenticadores, paginadores, parsers y adaptadores.
Modelar variaciones en tres niveles: plataforma, configuración de tienda y
override específico.

Los límites internos distinguirán control plane, ejecución, conectores,
normalización y persistencia aunque inicialmente compartan despliegue.

## Consecuencias

- Una corrección de plataforma puede beneficiar a múltiples tiendas.
- Los tests de contrato pueden aplicarse a todos los conectores.
- Los límites permiten extraer servicios más adelante con menor reescritura.
- Se requiere disciplina para evitar dependencias cruzadas entre módulos.
- Los overrides deben permanecer pequeños; si crecen, se evaluará un conector
  independiente.

## Alternativas descartadas

- Un repositorio o proceso independiente por tienda: maximiza duplicación.
- Microservicios desde el inicio: incrementa operación y contratos distribuidos
  sin una necesidad medida.
- Una jerarquía profunda de clases: hace frágiles las variaciones de tiendas.
