# Plan de implementación

## Diseño

- `DES-001`: capas según
  [ADR-0003](../../adr/0003-store-definitions-component-publication.md), que
  refina el nivel "configuración de tienda" de ADR-0001.
  - **Núcleo:** `contracts`, `models`, `config`, `runner`, `storage`,
    `transport`, `quality`, `observability` y `session`. No importa
    `ndevscrap.stores` ni `ndevscrap.connectors`, ni por import absoluto ni
    relativo.
  - **Plataforma:** `connectors/vtex.py` con `VtexSettings`. No importa
    `ndevscrap.stores` ni `connectors.clubdia`. Sigue la
    [ficha de VTEX](../../platforms/vtex/README.md).
  - **Tienda:** `stores/dia.py` compone plataforma y adaptadores propios.
    `connectors/clubdia.py` es exclusivo de DIA; queda en `connectors/` como
    ubicación transitoria registrada en ADR-0003.
  - **Raíz de composición:** la CLI y el registro `stores/__init__.py`.
  - **Dirección de imports del núcleo:** `contracts -> quality -> models`,
    `config -> contracts` y `transport -> contracts, config`. `quality` no
    importa `contracts`. `runner` puede importar cualquier módulo del núcleo.
- `DES-002`: `ComponentSpec` describe un componente ejecutable y
  `StoreDefinition` es un protocolo. La definición:
  - valida su configuración;
  - expone su configuración pública, incluido `session_configured`;
  - construye sus componentes a partir del transporte.

  `run_store` valida la composición antes de crear archivos, y toda violación
  es `ValueError`:
  - `store_id` y cada `name` cumplen `[a-z0-9][a-z0-9_-]*`, no son nombres de
    dispositivo de Windows (`con`, `nul`, `aux`, `prn`, `com1`…`com9`,
    `lpt1`…`lpt9`) y los nombres son únicos;
  - cada `output_file` es `<base>.jsonl` con una base que cumple la misma regla,
    y es único sin distinguir mayúsculas;
  - hay exactamente un componente crítico, que tiene conector, no está
    `unavailable`, no es `sensitive` y persiste raw;
  - `sensitive` implica `persist_raw=False`;
  - sólo el crítico puede declarar `quality`;
  - un componente sin conector declara `unavailable`;
  - `metadata` coincide con `connector.metadata` cuando hay conector;
  - `timezone` es una zona válida: `ZoneInfoNotFoundError` se convierte en
    `ValueError`.
- `DES-003`: `FileSnapshotStore` recibe `components: Mapping[str,
  StoredComponent]`, con archivo y marca `critical`. Generaliza lo existente
  sin cambiar la semántica de 0005:
  - `write_normalized(component, rows)` se llama **una sola vez por
    componente** con un iterable perezoso. Escribe `normalized/<archivo>.tmp`,
    hace `fsync` y `os.replace` al agotarse el iterable. Ante una excepción
    elimina el temporal y la propaga.
  - `published_count(component)` reemplaza a `previous_product_count` con la
    misma precedencia: índice, filas de current, `None`.
  - `publish(manifest, *, outcome, published)` reemplaza a `catalog_outcome` y
    `publish_coupons`. Antes de tocar el disco valida que `published` sólo
    contenga componentes declarados y que el crítico esté en `published` si y
    sólo si `outcome == "accepted"`; si no, `ValueError`. `outcome` decide
    `<fecha>/`, `attempts/` o staging retenido como en `DES-003` de 0005.
  - En `failed_transient`, `attempts/<fecha>/<run_id>/` recibe el manifest y
    los archivos normalizados de los opcionales publicados.
  - Current conserva las entradas del índice que la definición ya no declara
    sólo si su `file` cumple la regla de `output_file`, existe en `current/` y no
    coincide con el archivo de un componente declarado, que siempre prevalece.
    Las demás entradas se descartan.
- `DES-004`: el runner ejecuta los componentes en el orden declarado, cada uno
  aislado como en `DES-007` de 0005. Por componente arma un generador perezoso
  y lo entrega en una única llamada a `write_normalized`. El generador:
  1. llama a `discover`;
  2. por ítem, usa `prefetched`; si no hay, `read_raw` cuando `persist_raw`; si
     tampoco, `extract`;
  3. aplica `normalize` y materializa sólo la tupla de la página;
  4. si `persist_raw`, llama a `write_raw` tras normalizar sin error, o a
     `write_rejected` si `normalize` falla;
  5. entrega las filas de la página a la compuerta de calidad, que las cede a
     `write_normalized` antes de avanzar al siguiente ítem.

  Con `persist_raw=False` nunca se llama a `read_raw`, `write_raw` ni
  `write_rejected`.
- `DES-005`: `QualityGate` filtra en streaming:
  - aplica el validador; para el catálogo es `valid_product`, la función
    pública que reemplaza a `_valid`;
  - descarta duplicados con un `set` de claves y conserva la primera aparición;
  - cuenta `discovered`, `rejected` y `duplicates`.

  Al terminar, `evaluate_counts(valid, discovered, rejected, baseline,
  policy)` aplica `QualityPolicy(min_valid=1, max_invalid_percent=5,
  max_drop_percent=30)` con aritmética entera:
  - falla con `valid < min_valid`;
  - falla con `rejected * 100 > discovered * max_invalid_percent`;
  - si hay línea base mayor que cero, falla con
    `valid * 100 < baseline * (100 - max_drop_percent)`.

  Los mensajes interpolan los porcentajes de la política y, con los valores por
  defecto, son idénticos a los actuales ("catalog contains zero valid
  products", "exceeds 5 percent", "dropped more than 30 percent from N"). Una
  tienda nueva verá la palabra "product" en ellos. Un componente sin política
  ni clave, como ClubDIA, sólo cuenta filas.
- `DES-006`: clasificación genérica de errores con la etiqueta del componente.
  - `AuthenticationRequiredError`, en `contracts.py`, es la base de
    `SessionConfigurationError` y de `ClubDiaAuthenticationError`.
  - En un componente `sensitive` se aplican los mensajes fijos de 0005 con
    `<Etiqueta>`, en este orden:
    - `AuthenticationRequiredError`:
      `"<Tipo>: <Etiqueta> session unavailable or rejected"`
      (`authentication_required`);
    - `HttpStatusError` `3xx`, `401` o `403`:
      `"<Etiqueta> session rejected with HTTP <código>"`
      (`authentication_required`);
    - otro `HttpStatusError`: `"<Etiqueta> request failed with HTTP <código>"`;
    - `OSError`, `RuntimeError`, `TypeError` o `ValueError`:
      `"<Tipo>: <Etiqueta> request failed"`;
    - cualquier otra excepción: `"<Tipo>: unexpected <Etiqueta> failure"`.
  - En un componente no sensible se registra `"<Tipo>: <mensaje>"`. Los
    mensajes del transporte son fijos y no contienen material de sesión.
  - `unavailable` produce `authentication_required` con ese texto. Para DIA es
    `"Set NDEVSCRAP_DIA_SESSION_FILE to include ClubDIA coupons"`.
- `DES-007`: el desenlace del crítico sigue `DES-003` de 0005.
  - `accepted` o `quarantined` según la calidad.
  - `failed_transient` en dos casos:
    - un `TransportError` que no es `HttpStatusError`,
      `RequestBuildError` ni `UnexpectedRedirectError` (incluye red, timeout
      y el tope de `Retry-After`);
    - un `HttpStatusError` con código de `RETRYABLE_STATUS_CODES` tras agotar
      reintentos.
  - `failed` en cualquier otro caso, incluidos `RequestBuildError` y
    `UnexpectedRedirectError`.

  El estado global es:
  - `failed` si el crítico no terminó en `success`;
  - si no, `partial_success` si algún opcional no terminó en `success`;
  - si no, `success`.

  `published` contiene el crítico sólo si fue `accepted` y cada opcional en
  `success`.
- `DES-008`: `VtexSettings(base_url, locale="es-AR", currency="ARS",
  sales_channel=1, page_size=50, max_pages=50)` valida:
  - `base_url` HTTPS absoluta, sin credenciales en la URL, query ni fragmento;
    se quita la barra final antes de validar y se rechaza cualquier path
    distinto de vacío;
  - `1 <= page_size <= 50`;
  - `1 <= max_pages <= 50`.

  La capacidad segura de una partición es `page_size × max_pages`. El
  conector usa `context.postal_code` para `zip-code`.
- `DES-009`: `stores/dia.py` define `DiaSettings`, que valida en
  `from_environment(environ)`:
  - `base_url` desde `NDEVSCRAP_DIA_BASE_URL`, con el valor actual por defecto
    y las reglas de `DES-008`;
  - `session_file` desde `NDEVSCRAP_DIA_SESSION_FILE`, sin fallback implícito;
  - `country="ARG"` y la zona `America/Argentina/Buenos_Aires`;
  - un `VtexSettings`.

  `DiaStore(settings)` implementa `StoreDefinition` con `store_id="dia"` y
  `platform="vtex"`, y compone:
  - `catalog` / `products.jsonl`: `VtexConnector`, crítico, `persist_raw`,
    `valid_product`, clave `(sku_id, seller_id)` y `QualityPolicy()`;
  - `clubdia` / `coupons.jsonl`: `ClubDiaConnector` con
    `JsonFileSessionProvider`, opcional, `sensitive`, sin raw; sin
    `session_file` queda `unavailable`.

  `public_settings()` incluye `base_url`, país, `VtexSettings` y
  `session_configured`. `stores/__init__.py` expone
  `REGISTRY = {"dia": DiaStore.from_environment}`.
- `DES-010`: `stores/dia_session.py` recibe `extract_session_from_har` y las
  constantes de ClubDIA desde `session.py`. `session.py` conserva
  `JsonFileSessionProvider` con mensajes neutros (`"session file is unavailable
  or invalid"`) y `validate_session_output`, que acepta rutas fuera del
  repositorio o bajo `.secrets/`. El script:
  - escribe por defecto en `.secrets/dia-session.json`;
  - crea el directorio;
  - crea el archivo con `os.open(..., O_CREAT | O_WRONLY | O_TRUNC, 0o600)`,
    sin ventana previa a los permisos.

  En Windows rigen las ACL del perfil del usuario.
- `DES-011`: configuración.
  - `HttpSettings(timeout_seconds=20.0, requests_per_second=1.0,
    max_retries=3, max_retry_after_seconds=120.0)` valida los rangos de
    `REQ-006`. En `from_environment(environ)`:
    - una variable vacía equivale a no definida;
    - los flotantes rechazan `nan` e `inf`;
    - `max_retries` exige un entero decimal estricto (rechaza `"3.0"` y
      `"1e1"`);
    - el mensaje nombra la variable, nunca su valor.
  - `RunSettings(postal_code, output_dir, contact=None)` valida el código
    postal. `NDEVSCRAP_CONTACT`, si está definido, debe ser ASCII imprimible
    sin CR ni LF y de hasta 200 caracteres.
  - `build_transport(http, contact)` en `transport.py` crea `RequestsTransport`
    con User-Agent `NDevScrap/<__version__>` y agrega ` (+<contact>)` si hay
    contacto.
- `DES-012`: `RequestsTransport` endurecido.
  - **Sesión HTTP:** usa `trust_env=False`, así que no agrega credenciales de
    `.netrc` ni proxies del entorno. Los proxies están fuera de alcance.
  - **(a) Redirects:** todas las requests usan `allow_redirects=False`.
    - Si la request trae cookies o headers propios, un `3xx` se levanta como
      `HttpStatusError`.
    - Una request pública sigue a mano hasta 5 saltos, cada uno sujeto al
      rate limit, sólo si `Location` resuelve al mismo esquema HTTPS, host y
      puerto que la request original. Se valida antes de enviar, con el mismo
      parser que usa el envío (`requests` + `urllib3`), y se rechaza todo
      destino con credenciales, barra invertida o caracteres de control. La
      misma regla valida la URL base de `VtexSettings`.
    - Un salto a otro origen o a `http`, un `3xx` sin `Location` o más de 5
      saltos levantan `UnexpectedRedirectError` sin enviar nada más y sin
      reintento.
  - **(b) Errores de construcción:** `InvalidHeader`, `InvalidURL`,
    `MissingSchema`, `InvalidSchema` y `UnicodeError`.
    - Dentro del `except` sólo se guarda un indicador.
    - Fuera del bloque se levanta `RequestBuildError("HTTP request could not
      be built")`, sin reintento, con `__cause__` y `__context__` nulos.
    - Lo mismo aplica al agotamiento de reintentos por error de red:
      `TransportError("HTTP request failed after retries: <Tipo>")` fuera del
      `except`, sin referencia a la excepción ni al `PreparedRequest`.
  - **Espera fuera del `except`:** el bucle decide reintentar dentro del
    `except` y llama a `_retry` después de salir del bloque, sin excepción
    activa.
  - **(c) Cookies:** el jar de la `requests.Session`, propia o inyectada,
    recibe una política que rechaza toda cookie de respuesta, y se vacía
    después de cada request. Las únicas cookies enviadas son las de
    `HttpRequest`. La política y el vaciado son dos capas con pruebas y
    mutaciones propias.
  - **(d) Retry-After:**
    - un valor no finito o negativo se trata como ausente y se usa el backoff;
    - en un intento que todavía puede reintentar, un valor mayor que
      `max_retry_after_seconds` levanta `TransportError("Retry-After exceeds
      the configured maximum")` sin esperar y sin contar un reintento;
    - en el último intento prevalece el `HttpStatusError` del código, como
      hoy;
    - el formato fecha HTTP se calcula con un reloj de pared inyectable.
- `DES-013`: `stats()` devuelve un `TransportStats` inmutable, con
  `status_counts` como `MappingProxyType` de una copia:
  - `requests`: intentos iniciados, incluido cada salto de redirect enviado;
  - `retries`: esperas previas a un reintento, por backoff o `Retry-After`; el
    corte por tope no cuenta;
  - `status_counts`: respuestas recibidas por código, incluidas las
    reintentadas y cada salto de redirect.

  El runner toma `stats()` antes y después de cada componente, en un
  `finally`, y registra la diferencia.
- `DES-014`: `RunManifest` v2 y `ComponentResult` amplían los campos según
  `REQ-008`. `configuration_hash` es el SHA-256 del JSON canónico de:
  - tienda y plataforma;
  - `location.postal_code`;
  - `HttpSettings`;
  - `public_settings()` de la tienda;
  - `contact_configured` como booleano.

  No incluye la ruta de salida ni la ruta o el contenido de la sesión.
  `package_version` es `ndevscrap.__version__`.
- `DES-015`: `observability.py` define `JsonLogFormatter` y
  `configure_logging(stream=None)`.
  - `configure_logging` es idempotente: reemplaza sólo su propio handler, que
    identifica con una marca, y lo instala en el root con el `stream` indicado
    o `sys.stderr`. No toca handlers ajenos (por ejemplo, el de `caplog`).
    Activa `logging.captureWarnings(True)`.
  - Cada línea incluye `ts` en UTC, `level`, `logger` y `message`.
  - De los `extra`, sólo serializa los de una allowlist: `event`, `run_id`,
    `store`, `component`, `status`, contadores del componente y
    `duration_seconds`.
  - Si hay excepción, agrega `exc_type`.
  - Nunca serializa `exc_info`, traceback, `args` ni otros `extra`.
  - Los registros de loggers ajenos a `ndevscrap` (urllib3, `py.warnings`) se
    emiten con el mensaje fijo `"external log record"`, porque su mensaje
    interpolado puede contener headers crudos.

  El runner emite los eventos de `REQ-009` y elimina el log de traceback en
  `DEBUG` de 0005. La CLI configura el logging al empezar. Los errores previos
  a la corrida no tienen `run_id`. Un `except Exception` final registra sólo
  `exc_type` y devuelve `1`. Los mensajes de uso de argparse, como una tienda
  desconocida con código `2`, siguen saliendo como texto.

## Contratos

```python
SnapshotOutcome = Literal["accepted", "quarantined", "failed", "failed_transient"]


class AuthenticationRequiredError(RuntimeError): ...


class NormalizedRecord(Protocol):
    def to_dict(self) -> dict[str, Any]: ...


NormalizedT = TypeVar("NormalizedT", bound=NormalizedRecord)


@dataclass(frozen=True, slots=True)
class TransportStats:
    requests: int = 0
    retries: int = 0
    status_counts: Mapping[int, int] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def since(self, before: TransportStats) -> TransportStats: ...


class Transport(Protocol):
    def request(self, request: HttpRequest) -> HttpResponse: ...
    def stats(self) -> TransportStats: ...


@dataclass(frozen=True, slots=True)
class ComponentSpec:
    name: str  # clave en manifest, índice y raw/
    label: str  # etiqueta en mensajes
    output_file: str  # archivo en normalized/ y current/
    metadata: ConnectorMetadata
    connector: Connector[Any] | None
    critical: bool
    persist_raw: bool
    sensitive: bool = False
    unavailable: str | None = None
    validator: Callable[[Any], bool] | None = None
    record_key: Callable[[Any], Hashable] | None = None
    quality: QualityPolicy | None = None  # definida en quality.py


class StoreDefinition(Protocol):
    store_id: str
    platform: str
    timezone: str

    def validate(self) -> None: ...
    def public_settings(self) -> Mapping[str, Any]: ...
    def components(self, transport: Transport) -> Sequence[ComponentSpec]: ...


@dataclass(frozen=True, slots=True)
class StoredComponent:
    output_file: str
    critical: bool


class FileSnapshotStore:  # storage.py
    def __init__(
        self,
        output_dir: Path,
        *,
        store: str,
        postal_code: str,
        snapshot_date: date,
        run_id: str,
        components: Mapping[str, StoredComponent],
    ) -> None: ...


class SnapshotStore(Protocol):
    def prepare(self) -> None: ...
    def write_raw(self, component: str, record: RawRecord) -> None: ...
    def write_rejected(self, component: str, record: RawRecord) -> None: ...
    def read_raw(self, component: str, key: str) -> RawRecord | None: ...
    def write_normalized(
        self, component: str, rows: Iterable[NormalizedRecord]
    ) -> int: ...
    def published_count(self, component: str) -> int | None: ...
    def publish(
        self,
        manifest: RunManifest,
        *,
        outcome: SnapshotOutcome,
        published: AbstractSet[str],
    ) -> Path: ...
    def abort(self) -> None: ...


def run_store(
    definition: StoreDefinition,
    run_settings: RunSettings,
    http_settings: HttpSettings,
    *,
    transport: Transport | None = None,
    clock: Callable[[], datetime] | None = None,
) -> tuple[RunManifest, Path]: ...
```

- Desaparecen, y cada caller y cada implementación se actualizan juntos:
  - `CatalogOutcome`;
  - `write_products`, `write_coupons` y `previous_product_count`;
  - `run_dia` y `DiaConfig`;
  - `Transport.retries`;
  - el `TypeVar` restringido a `ProductSnapshot` y `CouponSnapshot`.

  `contracts.py` importa de `models` sólo `RunManifest`.
- Nuevos errores en `transport.py`: `RequestBuildError(TransportError)` y
  `UnexpectedRedirectError(TransportError)`.
- `quality.py` expone `QualityPolicy`, `QualityGate`, `evaluate_counts` y
  `valid_product`. `evaluate_products` desaparece.
- Manifest v2, ejemplo abreviado:

```json
{
  "schema_version": "2",
  "run_id": "…",
  "snapshot_id": "dia:1806:2026-09-26",
  "platform": "vtex",
  "store": "dia",
  "location": {"postal_code": "1806"},
  "package_version": "0.1.0",
  "configuration_hash": "…",
  "status": "partial_success",
  "started_at": "…",
  "finished_at": "…",
  "duration_seconds": 12.3,
  "components": {
    "catalog": {
      "connector_id": "vtex-intelligent-search",
      "connector_version": "1.0.0",
      "status": "success",
      "discovered": 5540,
      "normalized": 5533,
      "rejected": 0,
      "duplicates": 7,
      "retries": 1,
      "requests": 120,
      "http_status_counts": {"200": 119, "503": 1},
      "duration_seconds": 11.9,
      "published": true,
      "errors": []
    }
  }
}
```

- `.env.example` documenta `NDEVSCRAP_HTTP_TIMEOUT_SECONDS=20`,
  `NDEVSCRAP_HTTP_REQUESTS_PER_SECOND=1`, `NDEVSCRAP_HTTP_MAX_RETRIES=3` y
  `NDEVSCRAP_HTTP_MAX_RETRY_AFTER_SECONDS=120`.
  `NDEVSCRAP_DIA_SESSION_FILE=.secrets/dia-session.json` queda comentada para
  que copiar el archivo no active ClubDIA.
- Cambios en la CLI:
  - conserva argumentos, default `1806`, códigos y línea final;
  - `choices` sale de `REGISTRY`;
  - el texto de ayuda de `--postal-code` deja de nombrar a DIA;
  - los logs pasan de texto a JSON por stderr.
- El User-Agent pasa de `NDevScrap/0.1 (<contacto>)` a
  `NDevScrap/0.1.0 (+<contacto>)`.

## Flujo de datos

1. La CLI configura los logs JSON y llama a la fábrica de `REGISTRY[store]`
   con `os.environ`. Construye `RunSettings` y `HttpSettings` desde el entorno
   y llama a `run_store`. Cualquier `ValueError` es un error de configuración
   con código `1`.
2. `run_store` valida `RunSettings`, `HttpSettings`, la definición y su zona.
   Crea `run_id`, `snapshot_id` y `RunContext` con el reloj de esa zona,
   construye el transporte si no se inyectó, obtiene los componentes y valida
   la composición según `DES-002`. Recién entonces crea `FileSnapshotStore` y
   llama a `prepare()`.
3. Para cada componente emite `component_started` y toma `stats()`. Ejecuta
   `DES-004` y `DES-005` dentro de su manejo de errores `DES-006`. Luego
   calcula `duration_seconds` y la diferencia de `stats()`, y emite
   `component_finished`.
4. Con `DES-007` arma el estado, `published` y el manifest v2, y llama a
   `publish()`. Por último emite `run_finished` y devuelve el manifest y la
   ruta.
5. `publish()` aplica la semántica de 0005 sobre los archivos declarados.

## Fallos y recuperación

- **Configuración inválida** (tienda, zona, `HttpSettings`, `RunSettings`,
  `VtexSettings` o composición): `ValueError` antes de `prepare()`, sin crear
  archivos.
- **Fallo transitorio del crítico** (red, timeout, `429` o `5xx` reintentables
  agotados, `Retry-After` excesivo): staging retenido para reanudar. El layout
  del staging no cambia, así que esta versión reanuda un staging retenido por
  la de 0005.
- **Fallo estructural o permanente del crítico** (incluidos
  `RequestBuildError` y `UnexpectedRedirectError`): staging completo en
  `attempts/`, sin archivo normalizado parcial gracias a `DES-003`.
- **Redirect, `401` o `403` en ClubDIA:** `authentication_required`, cupones de
  current intactos y corrida `partial_success`.
- **Excepción no prevista fuera de los componentes** (por ejemplo, en
  `publish`): la CLI registra sólo su tipo y devuelve `1`.
- **Rollback:** revertir los commits. Los manifests v2 en `<fecha>/` y
  `attempts/` quedan inertes para el código anterior, que de ellos sólo lee
  `run_id`. El índice de current no cambia de formato y un staging retenido se
  reanuda igual.
- **Riesgos aceptados:**
  - la deduplicación conserva la primera aparición en lugar de la última;
  - quien leía logs de texto debe adaptar su lectura;
  - `trust_env=False` ignora proxies y certificados del entorno
    (`HTTPS_PROXY`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE`), lo que afecta a
    redes con inspección TLS; se documenta en el README;
  - rechazar `Set-Cookie` puede romper ClubDIA si el servidor rota cookies
    entre `token-by-user` y `cupons`. Se verifica en el smoke de `0008`; si
    falla, el conector propagará esas cookies dentro de su `extract`, sin
    tocar el jar;
  - los riesgos operativos de 0005 (retención, concurrencia y
    `.current.backup`) siguen fuera de alcance.

## Pruebas

- **Red de seguridad (`AC-001`):** `tests/test_runner.py`,
  `tests/test_storage.py` y `tests/test_cli.py` se adaptan a `run_store`,
  `write_normalized`, `published_count`, `publish(outcome, published)`,
  `stats()` y a una definición DIA construida con `DiaSettings` y
  `VtexSettings` de prueba.
  - Cada aserción se conserva.
  - Los datos de `connector_version` y `postal_code` de nivel superior de
    `tests/test_cli.py` y `tests/test_storage.py` pasan a sus equivalentes v2.
  - Las dos pruebas que llamaban a `_run_clubdia` pasan a ejecutar el
    componente ClubDIA mediante `run_store`.
- **`tests/test_storage.py` (`AC-002`):**
  - componente `items` con archivo `items.jsonl`;
  - `published_count` por componente;
  - `ValueError` sin tocar el disco ante un componente no declarado o
    inconsistente con `outcome`;
  - ausencia de archivo normalizado tras una excepción a mitad del stream;
  - `failed_transient` con opcional publicado;
  - entrada del índice con `file` `../x.jsonl` descartada y entrada colisionada
    con un componente declarado.
- **`tests/test_stores.py` (`AC-003`, `AC-004`, `AC-011`):**
  - imports del núcleo y de `connectors/vtex.py` analizados con `ast`,
    resolviendo imports relativos;
  - en un subproceso, `import ndevscrap.runner` no carga `ndevscrap.stores`;
  - registro con `dia`;
  - definición falsa de un componente con `run_store`;
  - cada regla de `DES-002`, sin directorio de salida;
  - forma de la definición DIA;
  - `session.py` sin `club-dia` ni `ClubDIA`;
  - sesión implícita en `.secrets/` ignorada.
- **`tests/test_vtex_connector.py` (`AC-005`):** construcción con
  `VtexSettings`, `zip-code` tomado de `RunContext` con un código distinto del
  default y `base_url` con credenciales, query, fragmento o path rechazada.
- **`tests/test_runner.py` (`AC-004`, `AC-006`, `AC-008`, `AC-009`,
  `AC-010`):**
  - fixture de dos particiones y dos páginas con duplicado y fila inválida;
  - monkeypatch de `FileSnapshotStore.write_normalized` que registra cada fila
    que extrae del iterable, intercalada con las requests del transporte;
  - `503` agotado en el catálogo con staging retenido;
  - fallo estructural de ClubDIA sin raw ni rechazados;
  - `302` de ClubDIA;
  - campos v2 y estadísticas por componente;
  - hash con otra ruta de sesión;
  - logs JSON capturados en un stream inyectado, con centinelas.
- **`tests/test_quality.py` (`AC-006`):** `QualityGate` y `evaluate_counts` en
  los límites exactos de 5% y 30%, el primer valor por encima, cero válidos y
  línea base `0` o `None`.
- **`tests/test_config.py` (`AC-007`, `AC-009`):**
  - defaults;
  - lectura de entorno y variable vacía;
  - rangos inválidos parametrizados, con `nan`, `inf`, `"3.0"` y `"1e1"`;
  - mensaje sin el valor;
  - contacto con CR/LF, no ASCII o demasiado largo;
  - hash.
- **`tests/test_cli.py` (`AC-007`, `AC-010`):**
  - código `1` con `NDEVSCRAP_HTTP_*` inválido, sin invocar `run_store`;
  - excepción inesperada registrada sólo por tipo;
  - tienda desconocida rechazada por argparse.
- **`tests/test_transport.py` (`AC-008`):** sobre `RequestsTransport` real con
  una `requests.Session` y un adapter falso montado en `https://` y en
  `http://`. El adapter construye la respuesta con
  `HTTPAdapter.build_response` sobre un `urllib3.HTTPResponse` con
  `original_response`, para que requests procese `Set-Cookie`.
  - (a) redirect con sesión (una request, sin cookie hacia el `Location`),
    redirect público al mismo origen seguido con cada salto en `stats()`, y
    redirect público a otro origen, a `http`, sin `Location` o con más de 5
    saltos rechazado sin que el adapter reciba ninguna request hacia el
    destino;
  - (b) errores de construcción parametrizados con un intento, `__cause__` y
    `__context__` nulos y ningún centinela en `traceback.format_exception`
    (el `UnicodeEncodeError` real nace en `http.client` durante el envío; el
    adapter falso lo levanta para simular esa ruta);
    agotamiento por red con `__context__` nulo; `sleep` que afirma
    `sys.exc_info() == (None, None, None)`;
  - (c) `Set-Cookie` ignorado, con una prueba de control que demuestra que el
    harness sí guarda la cookie en un jar sin la política; prueba unitaria de
    la política con `extract_cookies` sobre el jar sin vaciar; y una cookie
    colocada a mano en el jar desaparece tras la request;
  - (d) tope de `Retry-After` antes del último intento, `HttpStatusError` en el
    último, valores `nan` y negativos, y fecha HTTP;
  - backoff exponencial con jitter, agotamiento, `Timeout`, `ConnectionError`,
    `503` recuperado, espaciado del rate limit y `stats()`;
  - `trust_env`: con un `NETRC` temporal que tiene credenciales para el host,
    ningún `Authorization` llega al adapter.

  El `FakeSession` actual se reemplaza por este harness.
- **`tests/test_observability.py` (`AC-010`):** allowlist de campos, `exc_type`
  sin traceback, descarte de `extra` no permitidos, idempotencia y
  convivencia con `caplog`.
- **`tests/test_extract_dia_session.py` (`AC-011`):**
  - import desde `ndevscrap.stores.dia_session`;
  - `.secrets/` aceptado, `output/` rechazado y ruta externa aceptada;
  - permisos `0600` sólo en POSIX.
- **Mutaciones puntuales** fuera del repositorio, registradas en
  `validation.md`:
  - reactivar redirects en requests con sesión;
  - aceptar un redirect público a otro origen;
  - quitar la política de cookies;
  - quitar el vaciado del jar;
  - quitar `trust_env=False`;
  - reintentar errores de construcción;
  - levantar `RequestBuildError` dentro del `except`;
  - esperar dentro del `except`;
  - quitar el tope de `Retry-After`;
  - conservar la última aparición de un duplicado;
  - importar `ndevscrap.stores` desde el runner;
  - escribir raw de un componente `sensitive`;
  - clasificar un `503` agotado como `failed`.
- **Revisiones independientes:** `personal-sdd-qa` de contrato y
  `personal-sdd-qa` de seguridad sobre transporte, sesión y logs.

## Despliegue

No hay migración de datos: el layout, el índice de current y el staging son
compatibles, y la primera corrida escribe manifests v2.

Se actualizan:

- [ADR-0003](../../adr/0003-store-definitions-component-publication.md), que
  pasa a `accepted` con la aprobación, y su entrada en el índice de ADR;
- `.env.example`, `.gitignore` y `.dockerignore`;
- en `README.md`, las secciones de sesión (incluida la ruta `output/secrets/`),
  configuración HTTP y logs; la reescritura completa queda para 0007;
- `0004-dia-vtex-connector/validation.md`, con la nota de que 0006 cierra las
  brechas de `REQ-003`, `REQ-008` y `REQ-009`.

Quien tenga la sesión en `output/secrets/dia-session.json` puede seguir
usándola si apunta la variable a esa ruta, aunque se recomienda moverla a
`.secrets/`. La suite se ejecuta en Windows y en CI Ubuntu. La evidencia real
queda para `0008-release-v0-1-0`.
