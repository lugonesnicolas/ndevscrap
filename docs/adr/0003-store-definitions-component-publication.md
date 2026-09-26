# ADR-0003: Definiciones de tienda y publicación por componente

- Estado: `accepted`
- Fecha: 2026-09-26
- Iniciativa: [0006-store-composition](../sdd/0006-store-composition/spec.md)

## Contexto

ADR-0001 modela las variaciones como plataforma, configuración de tienda y
override. La primera tienda, DIA, se implementó con un orquestador propio que
conoce sus dos componentes (catálogo VTEX y cupones ClubDIA), un almacenamiento
con métodos de productos y cupones y un conector de plataforma que recibe la
configuración de DIA. Agregar una tienda exigiría modificar el orquestador, el
almacenamiento y la plataforma.

La iniciativa [0005-run-integrity](../sdd/0005-run-integrity/spec.md)
estableció que current se publica por componente, con procedencia propia, y que
sólo el desenlace del catálogo decide el snapshot fechado.

## Decisión

Esta decisión refina el nivel "configuración de tienda" de ADR-0001.

- Una **definición de tienda** es el único lugar que conoce la tienda. Declara
  su identidad, su plataforma, su zona horaria, su configuración pública y una
  lista ordenada de **componentes**.
- Un componente declara:
  - nombre, etiqueta y archivo de salida;
  - conector;
  - si es crítico;
  - si persiste raw;
  - si maneja material de sesión;
  - validador, clave de deduplicación y política de calidad.
- Cada tienda tiene exactamente un componente crítico. Su desenlace decide si el
  snapshot fechado se reemplaza, va a `attempts/` o queda en staging para
  reanudar. Los componentes opcionales se publican en current de forma
  independiente y, si fallan, degradan la corrida a éxito parcial.
- Un componente que maneja material de sesión no persiste raw ni páginas
  rechazadas, y sus errores se registran con mensajes fijos.
- Núcleo, plataforma y tienda:
  - el núcleo (contratos, runner, almacenamiento, transporte, calidad,
    configuración, sesión y observabilidad) no importa tiendas ni conectores;
  - un conector de plataforma recibe su propia configuración tipada y toma la
    ubicación del contexto de ejecución;
  - la CLI y el registro de tiendas son la raíz de composición.
- El almacenamiento de snapshots opera por componente. El formato del índice de
  current no cambia. Si una definición deja de declarar un componente, current
  conserva su entrada sólo si su archivo tiene un nombre seguro, existe y no
  coincide con el de un componente declarado, que siempre prevalece.
- Un adaptador exclusivo de una tienda pertenece a la capa de tienda.
  `connectors/clubdia.py` queda en `connectors/` de forma transitoria para
  acotar el cambio; el núcleo no lo importa.

## Consecuencias

- Una tienda nueva sobre una plataforma existente se agrega con una definición
  y una entrada de registro, sin tocar el núcleo.
- Las pruebas de reusabilidad pueden ejecutar una definición falsa sobre el
  runner real.
- La regla de un único componente crítico simplifica el ciclo de vida del
  snapshot. Una tienda con dos fuentes igual de críticas necesitará revisar
  esta decisión.
- La clasificación de errores sensibles depende de que la definición marque
  correctamente sus componentes; la validación de la composición rechaza un
  componente sensible que persista raw.
- Los mensajes y nombres de archivo de DIA se conservan porque salen de su
  definición.
- Un componente crítico no puede manejar material de sesión, porque sin raw
  persistido no podría reanudarse.

## Alternativas descartadas

- Mantener un orquestador por tienda: duplica aislamiento, publicación y
  observabilidad en cada tienda.
- Un `SnapshotStore` con métodos por tipo de entidad: obliga a modificar el
  almacenamiento por cada componente nuevo.
- Varios componentes críticos con un snapshot fechado por componente: complica
  la reanudación y la procedencia sin una tienda que lo necesite.
- Plugins descubiertos dinámicamente por entry points: agrega mecanismo sin
  necesidad con una sola tienda.
