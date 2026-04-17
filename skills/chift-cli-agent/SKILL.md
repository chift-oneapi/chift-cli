---
name: chift-cli
description: Use when you need to interact with the chift API, including authentication, endpoint discovery, schema inspection, parameter passing, and output filtering. Prefer this skill whenever the task mentions chift-cli, `chift ...`, Chift API endpoints, accounting, pos, pms, banking, invoicing, payment, ecommerce or automating Chift calls.
---

# Chift CLI Agent Guide

Prefer the installed executable:

```bash
chift ...
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
