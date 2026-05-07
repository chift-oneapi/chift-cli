# chift-cli

OpenAPI-driven CLI for the Chift API.

## Setup

```bash
uv sync
uv run chift --help
uv run chift auth setup
```

## Local Install

Install the CLI from this checkout when you want to run `chift` directly without `uv run`:

```bash
uv tool install .
chift --help
```

This installs a fixed build of the current checkout into uv's tool environment. Use this for normal local usage.

If you are developing the CLI and want the installed `chift` command to point at your working tree, install it in editable mode:

```bash
uv tool install --editable .
```

Editable installs are convenient for contributors because local source changes are reflected by the installed command. They are not recommended for regular users because the command can change or break as the checkout changes.

After switching between regular and editable installs, or after dependency changes, reinstall with `--force`:

```bash
uv tool install . --force
```

If you do not use uv, install with pip from a Python 3.11+ environment:

```bash
python -m pip install .
chift --help
```

For an isolated environment without uv:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install .
chift --help
```

For editable contributor installs without uv:

```bash
python -m pip install -e .
```

`auth setup` opens an interactive terminal form by default. You can skip the UI with flags:

```bash
uv run chift auth setup \
  --account-id <account_id> \
  --client-id <client_id> \
  --client-secret <client_secret>
```

or with environment variables:

```bash
CHIFT_ACCOUNT_ID=<account_id> \
CHIFT_CLIENT_ID=<client_id> \
CHIFT_CLIENT_SECRET=<client_secret> \
uv run chift auth setup
```

Check saved credentials without opening the setup form:

```bash
uv run chift auth check
```

## Environment

Environment variables are loaded once at process startup through `pydantic-settings`.

Common settings:

```bash
CHIFT_API_BASE_URL=http://chift.localhost:8000
CHIFT_OPENAPI_URL=http://chift.localhost:8000/openapi.json
CHIFT_CONFIG_DIR=/tmp/chift-config
CHIFT_CACHE_DIR=/tmp/chift-cache
CHIFT_ALLOWED_OPERATIONS=read,write
```

If `CHIFT_OPENAPI_URL` is not set, it is derived from `CHIFT_API_BASE_URL` and defaults to `/openapi.json`.

Set `CHIFT_ALLOWED_OPERATIONS` to a comma-separated list of operation classes when the CLI should only execute those classes for business vertical endpoints. Supported values are `read`, `write`, `dangerous`, and `all`; leaving it unset also allows all operations. Scope metadata takes precedence when it is present: an operation is `read` when any of its scopes ends in `.read`, otherwise broad-scoped non-`DELETE` operations are `write` and broad-scoped `DELETE` operations are `dangerous`. Without scopes, `GET`, `HEAD`, and `OPTIONS` are `read`; `POST`, `PUT`, and `PATCH` are `write`; and `DELETE` is `dangerous`. For example, `CHIFT_ALLOWED_OPERATIONS=read,write` rejects `DELETE` commands in verticals like `accounting`, `banking`, and `point-of-sale` before any request is built or sent. Platform and internal endpoint groups keep their full command set.

## Schema Cache

The command tree is generated from the OpenAPI schema. On first use, the CLI fetches and caches the schema automatically. You can refresh it manually:

```bash
uv run chift schema update
```

Inspect command groups:

```bash
uv run chift --help
uv run chift accounting --help
uv run chift accounting suppliers --help
```

## Endpoint Inputs

`consumer_id` is treated as route context and can be passed as the first positional value:

```bash
uv run chift accounting folders list <consumer_id>
```

Other inputs are passed as normal `KEY=VALUE` values:

```bash
uv run chift accounting suppliers get <consumer_id> supplier_id=<supplier_id> folder_id=<folder_id>
```

or with `--param`:

```bash
uv run chift accounting suppliers get <consumer_id> \
  --param supplier_id=<supplier_id> \
  --param folder_id=<folder_id>
```

`--param` and positional values are decoded as JSON when they look like a JSON literal (`true`, `false`, `null`) or start with `[` / `{`, so list and object body fields can be passed without `--json`:

```bash
uv run chift accounting suppliers create <consumer_id> --force \
  --param name=Acme \
  --param 'addresses=[{"address_type":"main","country":"BE","street":"...","city":"...","postal_code":"..."}]' \
  --param active=true
```

For full request bodies use `--json`. A required body field is treated as provided when its key is in the parsed `--json` object, so `--json` alone is enough for endpoints with required body fields:

```bash
uv run chift accounting suppliers create <consumer_id> --force \
  --json '{"name":"Acme","addresses":[{...}]}'
```

The CLI uses the OpenAPI schema to route values internally to path, query, or JSON body fields. Unknown params fail before the request is sent.

If required input is missing, the CLI prints a short usage hint. If endpoint-specific params are also required, it prints one merged JSON schema for those params.

Get only the merged input schema:

```bash
uv run chift accounting suppliers get --schema
```

## Output

API commands output JSON by default:

```bash
uv run chift accounting folders list <consumer_id>
```

Use YAML when needed:

```bash
uv run chift accounting folders list <consumer_id> --output yaml
```

Logs and debug details go to stderr:

```bash
uv run chift accounting folders list <consumer_id> --debug
```

`auth setup` and `auth check` are intentionally human-facing: they print a success message or a plain error message, not JSON.

## Filtering And Fields

`--fields` and `--filter` are client-side output helpers.

```bash
uv run chift accounting folders list <consumer_id> --fields id,name,parent.id
uv run chift accounting suppliers get <consumer_id> supplier_id=<id> --fields id,addresses.0.country
uv run chift accounting folders list <consumer_id> --filter name=Sales
uv run chift accounting clients list <consumer_id> --filter is_company=true --filter parent=null
```

`--fields` keeps selected fields after the response is received. For paginated responses (`{items, page, size, total}`) it is applied to each entry in `items`. Nested paths can include numeric indices to descend into arrays (`addresses.0.country`).

`--filter` filters list responses after the response is received. Multiple filters are ANDed together. Booleans and `null` are matched case-insensitively against their lowercase JSON form (`is_company=true`, `parent=null`). For paginated responses it filters `items` and updates `total`.

Pagination uses the API's own `page` and `size` query parameters; pass them as endpoint inputs:

```bash
uv run chift accounting suppliers list <consumer_id> page=2 size=50
```

## Schema Search

Search operations in the cached OpenAPI schema:

```bash
uv run chift schema search supplier
```

Search is currently substring-based. It checks operation JSON, paths, and summaries. It does not rank results and does not fully resolve component schemas for deep field search yet.

## Feature-Gated Endpoints

Some endpoint groups are hidden from help by default:

- `general`, `datastores`, `syncs`, `issues`, `m-c-p`, `webhooks`
- `consumers`, `integrations`

Enable internal endpoint groups:

```bash
CHIFT_SHOW_INTERNAL_ENDPOINTS=1 uv run chift --help
```

Enable platform endpoint groups:

```bash
CHIFT_SHOW_PLATFORM_ENDPOINTS=1 uv run chift --help
```
