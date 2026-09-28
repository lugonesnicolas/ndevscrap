# Operación de DIA Argentina

Esta guía describe la ejecución del conector DIA/VTEX ya implementado. La suite de pruebas no contacta DIA; una ejecución contra el sitio debe realizarse sólo cuando esté autorizada y sea necesaria para operar el pipeline.

## Ejecutar localmente

Se requiere Python 3.12 y `uv`:

```bash
uv sync --all-groups
uv run ndevscrap run dia --postal-code 1806 --output output
```

`--postal-code` define el contexto de precios y disponibilidad; su valor por defecto es `1806`. `--output` define la raíz local de los resultados y por defecto es `output`.

La CLI emite logs JSON por stderr y una única línea JSON por stdout. Sus códigos de salida son `0` para `success`, `2` para `partial_success` y `1` para un error de configuración, almacenamiento o ejecución.

## Salidas y publicación

Para DIA y el código postal `1806`, el almacenamiento queda bajo `<output>/dia/1806/`:

```text
<fecha>/                     snapshot crítico aceptado: raw, JSONL y manifest
attempts/<fecha>/<run_id>/   intentos no aceptados o snapshots reemplazados
current/                     último archivo publicado por componente e índice
.staging-<fecha>/            estado conservado tras un fallo transitorio
```

El catálogo es el componente crítico. Sólo reemplaza el snapshot fechado y su entrada en `current/` cuando supera los controles de calidad. La línea base de volumen se lee del catálogo publicado, no de intentos fallidos. ClubDIA es opcional: puede actualizar su `current/` de cupones por separado y un fallo no descarta un catálogo aceptado.

## Configuración de transporte

Copie los valores necesarios de [`.env.example`](../.env.example) a un archivo local que no se versiona o expórtelos en el entorno.

| Variable | Default | Rango |
| --- | ---: | --- |
| `NDEVSCRAP_DIA_BASE_URL` | URL pública de DIA | Origen HTTPS válido. |
| `NDEVSCRAP_CONTACT` | No definido | Contacto ASCII opcional para User-Agent. |
| `NDEVSCRAP_HTTP_TIMEOUT_SECONDS` | `20` | Mayor que 0 y hasta 300 s. |
| `NDEVSCRAP_HTTP_REQUESTS_PER_SECOND` | `1` | Mayor que 0 y hasta 2. |
| `NDEVSCRAP_HTTP_MAX_RETRIES` | `3` | Entero entre 0 y 10. |
| `NDEVSCRAP_HTTP_MAX_RETRY_AFTER_SECONDS` | `120` | Mayor que 0 y hasta 3600 s. |

Una variable inválida termina antes de crear resultados. El transporte no toma proxies, certificados ni credenciales `.netrc` del entorno; redes que requieren inspección TLS no están soportadas.

## ClubDIA y sesiones autorizadas

ClubDIA sólo se habilita al definir `NDEVSCRAP_DIA_SESSION_FILE` con una ruta explícita. El archivo no se busca automáticamente y nunca debe versionarse, aparecer en logs ni pasarse como argumento de la CLI.

Para renovar una sesión autorizada, inicie sesión en DIA, abra ClubDIA y exporte un HAR autorizado. Luego ejecute:

```bash
python scripts/extract_dia_session.py "captura-dia.har"
```

El script escribe por defecto en `.secrets/dia-session.json`. Git y Docker ignoran `.secrets/`; si el repositorio está dentro de una carpeta sincronizada, use una ruta local fuera del repositorio para reducir la exposición. Dentro del repositorio, el script sólo acepta archivos bajo `.secrets/`.

Las requests con sesión no siguen redirects y las cookies de respuesta no se persisten. Si la sesión falta o expira, el catálogo público puede publicarse y la corrida termina con éxito parcial.

## Docker

La imagen usa la misma CLI:

```bash
docker build -t ndevscrap .
docker run --rm -v ./output:/app/output ndevscrap run dia \
  --postal-code 1806 --output /app/output
```

Para ClubDIA, monte el archivo de sesión como secreto de sólo lectura y defina `NDEVSCRAP_DIA_SESSION_FILE` dentro del contenedor. No copie sesiones a la imagen ni las monte dentro del directorio de salida.
