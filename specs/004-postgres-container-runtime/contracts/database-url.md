# Contract: resolución de `DATABASE_URL`

**Feature**: H004  
**Component**: `create_incident_repository` en `src/adapters/outbound/factory.py`  
**Consumers**: `create_app()`, CLI `health` / `create` / `sla` / `summary`

## Entrada

1. Argumento explícito, si no es `None`.
2. Si el argumento es `None`, la variable de entorno `DATABASE_URL`.
3. Si la variable no existe, el default `sqlite:///:memory:`.

Antes de clasificar se recortan espacios de los extremos. El esquema se compara sin distinguir mayúsculas. El resto de la URL se conserva tal cual.

## Selección

| URL resuelta | Adaptador | Conecta en la fábrica |
| :--- | :--- | :--- |
| `sqlite:///` + path no vacío | `SQLiteIncidentRepository` | Sí (sqlite local: archivo o `:memory:`) |
| `postgresql://...` | `PostgresIncidentRepository` | No. El primer uso abre `psycopg` con `connect_timeout=3` |
| Ausente | SQLite `:memory:` | Sí |

Path SQLite: el texto que sigue a `sqlite:///` , con su caja original. `sqlite:///:memory:` sigue significando memoria.

## Rechazo inmediato

| Entrada | Excepción | Mensaje exacto |
| :--- | :--- | :--- |
| Definida y vacía, o solo espacios (argumento o variable) | `ValueError` | `DATABASE_URL está definida pero vacía.` |
| Esquema distinto, incluido `postgres://`, `sqlite://` sin tercera barra, o path SQLite vacío | `ValueError` | `Esquema de base de datos no soportado. Solo se admite sqlite:/// y postgresql://.` |

El mensaje no contiene el valor recibido. No se abre un adaptador y no se sustituye por memoria.

## Efecto en los canales

- **HTTP**: `create_app()` llama a la fábrica al construir la app. Un `ValueError` aborta el arranque; no hay servidor “a medias” sirviendo `/health` ni altas.
- **CLI**: el comando que llama a la fábrica imprime el mensaje en stderr y termina con exit `1`. No imprime JSON de salud.
- **`triage` / `audit`**: no llaman a la fábrica. Siguen operando sin almacén.

## Query de libpq

Una URL `postgresql://` puede incluir parámetros de libpq (`sslmode`, etc.). Se pasan completos a `psycopg`. El timeout de conexión del hito se fija por argumento del driver (`connect_timeout=3`), no reescribiendo la URL del operador.

## Fuera de este contrato

- No se acepta un tercer esquema.
- No se lee la URL desde un archivo de configuración versionado.
- El benchmark `src/incident_repository.py` no pasa por esta fábrica.
