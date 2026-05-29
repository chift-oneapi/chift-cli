---
name: chift-cli
description: Use when you need to interact with the chift API, including authentication, endpoint discovery, schema inspection, parameter passing, creating/updating records, and output filtering. Prefer this skill whenever the task mentions chift-cli, `chift ...`, Chift API endpoints, accounting, pos, pms, banking, invoicing, payment, ecommerce, consumer id or automating Chift calls.
---

# Chift CLI Agent Guide

Prefer the installed executable:

```bash
chift ...
```

If `chift` is not installed, install the latest released binary:

```bash
curl -fsSL https://raw.githubusercontent.com/chift-oneapi/chift-cli/master/install.sh | sh
```

## Authentication

Always start by checking whether you have saved credentials and that they are still valid:

```bash
chift auth check
```

If not always authenticate with explicit args if given by the user:

```bash
chift auth setup \
  --account-id <CHIFT_ACCOUNT_ID> \
  --client-id <CHIFT_CLIENT_ID> \
  --client-secret <CHIFT_CLIENT_SECRET>
```

If the user didn't give any credentials you can either ask him for the credentials or ask him to perform the following command on it's own :

```bash
chift auth setup
```

Never run `chift auth setup` yourself as an agent without the setting flags.

## Discovery

Use `--next` to navigate the command tree. It delegates to the most useful view at each level (`--help` for navigation, `--schema` for endpoint inputs):

```bash
chift --next                              # list available verticals
chift accounting --next                   # list entities in that vertical
chift accounting suppliers --next         # list commands for that entity
chift accounting suppliers get --next     # show the input schema for that command
```

Help is plain text:

```bash
chift --help
chift accounting --help
chift accounting suppliers --help
```

Search endpoint metadata:

```bash
chift schema search supplier
```

Search is substring-based over operation JSON, paths, and summaries. It is not ranked and does not deeply resolve all component schemas.

Inspect the full command tree:

```bash
chift schema tree
```

The command tree is generated from a cached OpenAPI schema. If an endpoint or path you expect is not present in the tree / help output, the cache may be stale — refresh it and retry:

```bash
chift schema update
```

If a command is still missing after refreshing, the installed CLI itself may be out of date. You may need to update it:

```bash
chift update
```

## Endpoint Inputs

`consumer_id` is route context. Pass it as the first positional value after the operation:

```bash
chift accounting folders list <consumer_id>
```

You can avoid passing it on every command by setting it once in the environment:

```bash
export CHIFT_CONSUMER_ID=<consumer_id>
chift accounting folders list
```

Pass all other endpoint inputs as normal `KEY=VALUE` arguments:

```bash
chift accounting suppliers get <consumer_id> supplier_id=<supplier_id> folder_id=<folder_id>
```

`--param KEY=VALUE` is also accepted:

```bash
chift accounting suppliers get <consumer_id> --param supplier_id=<supplier_id>
```

Unknown inputs fail before the request. If an error says `Unknown input parameter`, inspect accepted keys with `--schema`.

## Schema And Missing Inputs

Get the merged input schema only:

```bash
chift accounting suppliers get --schema
```

`--schema` intentionally omits `consumer_id` from params because it is context. It shows endpoint-specific params/body fields only.

If required input is missing, the CLI prints a short usage block and, when there are endpoint-specific params, a JSON schema for those params.

## Output

API commands output JSON by default. Use YAML only if requested:

```bash
chift accounting folders list <consumer_id> --output yaml
```

Logs and debug details go to stderr (they do not pollute parseable stdout):

```bash
chift accounting folders list <consumer_id> --debug
```

Keep API output small. Prefer endpoint params from `--schema`, small limits, selected fields, and shell tools for aggregate answers:

```bash
chift accounting suppliers list <consumer_id> --schema
chift accounting suppliers list <consumer_id> search=acme --fields id,name
chift accounting suppliers list <consumer_id> --fields id | jq 'length'
```

For quick existence checks, request only enough to answer. Pagination uses `page` and `size` (not `limit` / `cursor`):

```bash
chift accounting suppliers list <consumer_id> search=acme size=1 --fields id,name
```

Use `--fields` to reduce response size after the API response:

```bash
chift accounting folders list <consumer_id> --fields id,name,parent.id
```

Use `--filter` to filter list responses client-side:

```bash
chift accounting folders list <consumer_id> --filter name=Sales
```

`--filter` and `--fields` apply to top-level array responses and to paginated `{items, page, size, total}` envelopes (they target `items`).
API query parameters must be passed as endpoint inputs (`KEY=VALUE` or `--param KEY=VALUE`).

## Feature-Gated Endpoints

Some endpoint groups are hidden from help by default. If the user asks about a group you cannot see, enable it for that invocation:

```bash
CHIFT_SHOW_INTERNAL_ENDPOINTS=1 chift --help   # general, datastores, syncs, issues, m-c-p, webhooks
CHIFT_SHOW_PLATFORM_ENDPOINTS=1 chift --help   # consumers, integrations
```

## Error Handling

Exit codes:

- `0`: success
- `2`: argument or CLI usage error
- `3`: authentication error
- `4`: retry recommended

Auth errors surface Chift reasons when available. If auth fails with an accountId validation error, rerun non-interactive `auth setup` with a valid UUID account id.
