# chift-cli

OpenAPI-driven CLI for the Chift API.

## Setup

```bash
uv sync
uv run chift --help
uv run chift auth setup
```

## Install From GitHub Releases

Install the latest released binary:

```bash
curl -fsSL https://raw.githubusercontent.com/chift-oneapi/chift-cli/master/install.sh | sh
chift --help
```

Update an existing install:

```bash
chift update
```

## Local Install From Source

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

Environment variables are loaded once at process startup through `pydantic-settings`. Place them in a `.env` file in your working directory or export them in your shell. See `.env.example` for a template.

Key settings:

```bash
# API endpoint (defaults to https://api.chift.eu)
CHIFT_API_BASE_URL=https://api.chift.eu

# Default consumer — avoids passing consumer_id on every command
CHIFT_CONSUMER_ID=<consumer_id>

# Restrict which operation classes the CLI will execute
CHIFT_ALLOWED_OPERATIONS=read,write

# Show hidden endpoint groups
CHIFT_SHOW_PLATFORM_ENDPOINTS=1   # exposes consumers, integrations
CHIFT_SHOW_INTERNAL_ENDPOINTS=1   # exposes general, datastores, syncs, issues, m-c-p, webhooks
```

If `CHIFT_OPENAPI_URL` is not set, it is derived from `CHIFT_API_BASE_URL` and defaults to `/openapi.json`.

Set `CHIFT_ALLOWED_OPERATIONS` to a comma-separated list of operation classes when the CLI should only execute those classes for business vertical endpoints. Supported values are `read`, `write`, `dangerous`, and `all`; leaving it unset also allows all operations. Scope metadata takes precedence when it is present: read-only scopes allow `read`, broad scopes allow `write`, and broad `DELETE` operations require `dangerous`. Without scopes, `GET`, `HEAD`, and `OPTIONS` are `read`; `POST` and `PATCH` are `write`; and `DELETE` is `dangerous`. For example, `CHIFT_ALLOWED_OPERATIONS=read,write` rejects `DELETE` commands in verticals like `accounting`, `banking`, and `point-of-sale` before any request is built or sent. Platform and internal endpoint groups keep their full command set.

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

### Discovering what an endpoint needs

Use `--next` at any level to find out what to do next:

```bash
uv run chift --next                              # list available verticals
uv run chift accounting --next                   # list entities in that vertical
uv run chift accounting suppliers --next         # list commands for that entity
uv run chift accounting suppliers get --next     # show the input schema for that command
```

`--next` always delegates to the most useful view at that level: `--help` for navigation, `--schema` for endpoint inputs.

Run a command without required inputs and the CLI prints a usage hint and the merged JSON schema of expected parameters:

```bash
uv run chift accounting suppliers get
# => prints usage + schema showing required fields
```

Get only the schema without executing:

```bash
uv run chift accounting suppliers get --schema
```

### Passing inputs

`consumer_id` is treated as route context. Set it once via env var or pass it as the first positional argument:

```bash
export CHIFT_CONSUMER_ID=<consumer_id>
uv run chift accounting folders list

# or inline:
uv run chift accounting folders list <consumer_id>
```

Other path and query parameters are passed as `KEY=VALUE` positional values or with `--param`:

```bash
uv run chift accounting suppliers get <consumer_id> supplier_id=<supplier_id>

uv run chift accounting suppliers get <consumer_id> \
  --param supplier_id=<supplier_id> \
  --param folder_id=<folder_id>
```

### Posting data

For `POST` and `PATCH` operations pass a JSON body with `--json`, or use `KEY=VALUE` pairs which are merged into the request body:

```bash
# Using KEY=VALUE pairs (merged into JSON body)
uv run chift accounting suppliers create <consumer_id> \
  --force \
  name="Acme Corp" \
  currency_code=EUR

# Using raw JSON
uv run chift accounting suppliers create <consumer_id> \
  --force \
  --json '{"name": "Acme Corp", "currency_code": "EUR"}'
```

Mutating operations (`POST`, `PATCH`, `DELETE`) require `--force` to prevent accidental writes.

### Multiple parameters

Repeat `--param` or use `KEY=VALUE` pairs for endpoints with multiple inputs:

```bash
uv run chift accounting suppliers list <consumer_id> page=2 size=50

uv run chift accounting invoices get <consumer_id> \
  --param invoice_id=<id> \
  --param include_lines=true
```

The CLI routes each parameter to the correct location (path, query, or body) based on the OpenAPI schema. Unknown parameters are rejected before the request is sent.

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
uv run chift accounting folders list <consumer_id> --filter name=Sales
```

`--fields` keeps selected fields after the response is received. For paginated responses (`{items, page, size, total}`) it is applied to each entry in `items`.

`--filter` filters list responses after the response is received. Multiple filters are ANDed together. For paginated responses it filters `items` and updates `total`.

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
