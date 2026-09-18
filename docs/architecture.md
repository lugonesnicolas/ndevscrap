# Arquitectura de NDevScrap

## Contexto y objetivos

NDevScrap debe permitir incorporar y mantener muchas tiendas sin convertir cada
scraper en un proyecto independiente. La arquitectura optimiza reutilización,
aislamiento de fallos, trazabilidad, operación responsable y costo por ejecución.

Los objetivos iniciales son:

- ejecutar la misma lógica en local, contenedores y futuros runtimes cloud;
- reutilizar integraciones de plataforma entre múltiples tiendas;
- preservar un contrato de salida aunque cambie el mecanismo de acceso;
- detectar fallos técnicos y degradaciones de calidad;
- escalar componentes según su perfil de recursos.

No son objetivos de la fundación documental seleccionar un proveedor cloud,
implementar el scheduler ni definir prematuramente microservicios.

## Diseño de alto nivel

El punto de partida es un monolito modular. Sus límites internos anticipan dos
planos sin exigir despliegues separados:

```text
Control plane
configuración -> scheduler -> cola -> estado de ejecuciones
                                  |
Data plane                        v
workers HTTP / browser -> conectores -> validación -> almacenamiento
```

El control plane decidirá qué, cuándo y con qué configuración se ejecuta. El
data plane realizará la adquisición y transformación. Sólo se separarán en
servicios cuando el volumen, el aislamiento de fallos o los perfiles de recursos
lo justifiquen.

## Modelo de conectores

Un conector representa una capacidad de extracción, no un proceso completo de
infraestructura. El contrato conceptual mínimo es:

```python
class Connector(Protocol):
    metadata: ConnectorMetadata

    def discover(self, context) -> Iterable[SourceItem]: ...
    def extract(self, item, context) -> RawRecord: ...
    def normalize(self, record) -> Product: ...
```

`ConnectorMetadata` declarará identidad, versión, propietario, capacidades,
mecanismo de acceso, límites recomendados y versión del esquema de salida. La
configuración será tipada y externa a la lógica del conector.

La reutilización sigue tres niveles:

1. Un conector de plataforma implementa el comportamiento compartido, por
   ejemplo Shopify, Magento o WooCommerce.
2. La configuración de tienda aporta dominio, locale, moneda, categorías,
   credenciales y límites.
3. Un override contiene únicamente diferencias reales de una tienda.

Clientes HTTP, autenticadores, paginadores, parsers, rate limiters y escritores
se componen; no se construyen jerarquías profundas de clases. Los detalles se
formalizan en [ADR-0001](adr/0001-modular-connectors.md).

## Estrategia de adquisición

El mecanismo se elige en este orden:

1. API pública o autorizada.
2. HTML estático.
3. Navegador Playwright headless.

El navegador es un adaptador de adquisición, no una variante del contrato del
conector. Sus workers deben poder aislarse porque consumen más CPU y memoria.
La decisión completa está en [ADR-0002](adr/0002-api-first-browser-isolation.md).

## Ejecución y confiabilidad

Cada ejecución tiene identificador, versión de conector, configuración efectiva
y clave idempotente. Las unidades reintentables conservan checkpoints de cursor,
página o categoría para no reiniciar catálogos completos.

Los límites de concurrencia se aplican de forma jerárquica por plataforma,
dominio, credencial o sesión y endpoint. Los reintentos usan backoff con jitter,
respetan `Retry-After` y tienen un máximo explícito.

Los errores se clasifican como:

- transitorios: red, timeout, `429` o fallos recuperables del servidor;
- permanentes: recurso inválido o configuración incompatible;
- autenticación o autorización: requieren intervención y no se reintentan sin
  un cambio de credenciales;
- cambio de estructura: el contenido responde, pero rompe invariantes o parsing;
- calidad: la ejecución termina, pero el resultado es incompleto o anómalo.

Los trabajos agotados se conservan para diagnóstico y eventual reproceso. Una
ejecución reintentada no debe duplicar resultados.

## Datos y contratos

Los datos avanzan por tres capas:

- **raw:** respuesta original o referencia inmutable, más procedencia y fecha;
- **normalized:** entidades comunes como producto, variante, oferta, precio y
  stock, con esquema versionado;
- **current:** último estado consolidado para consumo.

La normalización conserva moneda, locale, zona horaria, timestamp de captura,
identidad de la fuente y atributos específicos en extensiones controladas. Un
cambio incompatible de esquema requiere migración documentada en el SDD.

## Observabilidad y calidad

Cada ejecución debe emitir logs estructurados y métricas con `run_id`, tienda,
conector y versión. Como mínimo se observarán duración, requests, latencia,
reintentos, códigos HTTP, elementos descubiertos, extraídos, rechazados y
modificados, uso de navegador y antigüedad del último resultado correcto.

La salud no se deduce sólo del exit code. Cero productos, un descenso anormal de
volumen o un aumento de campos nulos se consideran fallos de calidad y deben
generar evidencia diagnóstica.

## Seguridad y operación responsable

- Secretos y tokens provienen de configuración externa y nunca se registran.
- Se revisan términos de uso y `robots.txt` cuando corresponda.
- No se eluden autenticación, controles de acceso ni medidas antiabuso.
- Timeouts, límites y retención son explícitos por conector.
- Fixtures y logs deben eliminar o anonimizar datos sensibles.

## Estrategia de pruebas

La suite determinista utiliza fixtures locales y cubre parsers, normalización,
errores HTTP, paginación, idempotencia y formato de salida. Todos los conectores
deben superar pruebas de contrato. Los smoke tests reales se ejecutan por
separado sobre una muestra pequeña y controlada.

Cada cambio se especifica y valida mediante el [ciclo SDD](sdd/README.md).

## Cuándo revisar esta arquitectura

Se debe proponer un ADR cuando cambie un contrato transversal, un límite de
módulo, el modelo de datos, la estrategia de ejecución o la postura de seguridad.
La división en servicios se reconsiderará usando evidencia de volumen, costo,
aislamiento o necesidades de despliegue independiente.
