---
name: chift-cli-agent
description: Use when an AI agent needs to operate the chift CLI non-interactively against the Chift API, including authentication, endpoint discovery, schema inspection, feature flags, parameter passing, dry-runs, and output filtering. Prefer this skill whenever the task mentions chift-cli, `chift ...`, Chift API endpoints, or automating Chift CLI calls.
---

# Chift CLI Agent Guide

Prefer the installed executable:

```bash
chift ...
```

When developing inside the repository before installation, use:

```bash
uv run chift ...
```

Prefer non-interactive commands. Do not use the auth terminal UI in agent workflows.

## Authentication

Authenticate with explicit args:

```bash
chift auth setup \
  --account-id "$CHIFT_ACCOUNT_ID" \
  --client-id "$CHIFT_CLIENT_ID" \
  --client-secret "$CHIFT_CLIENT_SECRET"
```

If working in the repository before installation, prefix commands with `uv run`:

```bash
uv run chift auth setup \
  --account-id "$CHIFT_ACCOUNT_ID" \
  --client-id "$CHIFT_CLIENT_ID" \
  --client-secret "$CHIFT_CLIENT_SECRET"
```

or pass literal values if the caller provided them:

```bash
chift auth setup --account-id <account_id> --client-id <client_id> --client-secret <client_secret>
```

Never run bare `chift auth setup` as an agent unless the user explicitly wants the interactive TUI.

For local API instances, set:

```bash
CHIFT_API_BASE_URL=http://chift.localhost:8000
```

If `CHIFT_OPENAPI_URL` is not set, it derives from `CHIFT_API_BASE_URL` as `/openapi.json`.

## Feature Flags

Most verticals are visible by default. Hidden endpoint groups require env flags:

```bash
CHIFT_SHOW_INTERNAL_ENDPOINTS=1  # general, datastores, syncs, issues, m-c-p, webhooks
CHIFT_SHOW_PLATFORM_ENDPOINTS=1  # consumers, integrations
```

Set flags only when the task needs those groups.

## Discovery

Help is plain text:

```bash
chift --help
chift accounting --help
chift accounting suppliers --help
```

The command tree is generated from OpenAPI. The first command fetches and caches the schema automatically. Refresh manually when endpoint availability seems stale:

```bash
chift schema update
```

Search endpoint metadata:

```bash
chift schema search supplier
```

Search is substring-based over operation JSON, paths, and summaries. It is not ranked and does not deeply resolve all component schemas.

## Endpoint Inputs

`consumer_id` is route context. Pass it as the first positional value after the operation:

```bash
chift accounting folders list <consumer_id>
```

Pass all other endpoint inputs as normal `KEY=VALUE` arguments:

```bash
chift accounting suppliers get <consumer_id> supplier_id=<supplier_id> folder_id=<folder_id>
```

`--param KEY=VALUE` is also accepted:

```bash
chift accounting suppliers get <consumer_id> --param supplier_id=<supplier_id>
```

The CLI routes values internally to path, query, or JSON body based on the OpenAPI schema. Do not try to infer transport location yourself.

Unknown inputs fail before the request. If an error says `Unknown input parameter`, inspect accepted keys with `--schema`.

## Schema And Missing Inputs

Get the merged input schema only:

```bash
chift accounting suppliers get --schema
```

`--schema` intentionally omits `consumer_id` from params because it is context. It shows endpoint-specific params/body fields only.

If required input is missing, the CLI prints a short usage block and, when there are endpoint-specific params, a JSON schema for those params.

## Dry Runs

Use dry-run before calling unfamiliar or mutating endpoints:

```bash
chift accounting suppliers get <consumer_id> supplier_id=<supplier_id> --dry-run
```

Mutating endpoints require `--force`, unless using `--dry-run`:

```bash
chift accounting suppliers create <consumer_id> name="Acme" --dry-run
chift accounting suppliers create <consumer_id> name="Acme" --force
```

## Output

API commands output JSON by default. Use YAML only if requested:

```bash
chift accounting folders list <consumer_id> --output yaml
```

Use `--fields` to reduce response size after the API response:

```bash
chift accounting folders list <consumer_id> --fields id,name,parent.id
```

Use `--filter` to filter list responses client-side:

```bash
chift accounting folders list <consumer_id> --filter name=Sales
```

`--fields` and `--filter` are local post-processing. API query parameters must be passed as endpoint inputs (`KEY=VALUE` or `--param KEY=VALUE`).

## Error Handling

Exit codes:

- `0`: success
- `2`: argument or CLI usage error
- `3`: authentication error
- `4`: retry recommended

Auth errors surface Chift reasons when available. If auth fails with an accountId validation error, rerun non-interactive `auth setup` with a valid UUID account id.
