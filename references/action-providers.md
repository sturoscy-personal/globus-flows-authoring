# Globus-hosted action providers

Sources: https://docs.globus.org/api/flows/hosted-action-providers/ and https://docs.globus.org/api/transfer/action-providers/

Field lists below are the ones confirmed in the docs. Providers evolve, so when a field matters, introspect the provider or read its docs page:

```bash
curl 'https://transfer.actions.globus.org/transfer' | jq '.input_schema'
```

Introspection also reports who may run the provider and its scope.

## Contents
- Transfer family (current)
- Legacy Transfer providers (deprecated)
- Search
- Compute
- Notification email
- Wait for user selection
- Expression evaluation
- Other
- Custom action providers

## Transfer family (current)

Hosted at `transfer.actions.globus.org`. All use the Transfer API scope `urn:globus:auth:scope:transfer.api.globus.org:all`. They mirror the Transfer API closely.

| ActionUrl | Purpose | Key inputs | Where the result is |
|---|---|---|---|
| `https://transfer.actions.globus.org/transfer` | Submit a transfer | `source_endpoint`, `destination_endpoint`, `DATA` (list of items with `source_path`, `destination_path`, optional `recursive`) | `details` is a Transfer task document (`files`, `bytes_transferred`, `faults`, `nice_status`, ...) |
| `https://transfer.actions.globus.org/delete` | Delete data | `endpoint`, `DATA` (list of `{path}`), `recursive` | `details` is a task document |
| `https://transfer.actions.globus.org/ls` | List a directory | `endpoint_id`, `path`, optional filter and `show_hidden` | listing at `details.DATA` |
| `https://transfer.actions.globus.org/mkdir` | Make a directory | `endpoint_id`, `path` | `details.code` is `DirectoryCreated` on success |
| `https://transfer.actions.globus.org/stat` | Stat a file or directory | `endpoint_id`, `path` | `details.type` is `file` or `dir`, plus `size`, `last_modified` |
| `https://transfer.actions.globus.org/collection_info` | Collection metadata | collection ID | `details` is an endpoint document (`entity_type`, `subscription_id`, ...) |
| `https://transfer.actions.globus.org/manage_permission` | Manage ACLs on a guest collection | see docs page | |

Also available (see the Transfer action providers index): create a GCP guest collection and create a GCSv5 guest collection.

URL confidence: `/ls`, `/mkdir`, and `/collection_info` appear verbatim in the docs. `/transfer`, `/delete`, `/stat`, and `/manage_permission` follow the documented migration rule (old path under `actions.globus.org/transfer/` maps to the same name under `transfer.actions.globus.org/`, with `set_permission` renamed). Confirm with the introspection command above the first time you use one.

Notes:
- `recursive` is optional per transfer item now; Transfer auto-detects item type. Use `stat` when you need to branch on file versus directory.
- Optional transfer fields supported include `filter_rules`, `perf_cc`, `perf_p`, `perf_pp`, `perf_udt`, and `deadline`.
- Note the inconsistency between providers: transfer and delete take `source_endpoint`/`destination_endpoint`/`endpoint`, while ls, mkdir, and stat take `endpoint_id`. Check each provider's schema.

Example Transfer state:

```json
"Transfer": {
  "Type": "Action",
  "ActionUrl": "https://transfer.actions.globus.org/transfer",
  "Parameters": {
    "source_endpoint.$": "$.source.id",
    "destination_endpoint.$": "$.destination.id",
    "DATA": [
      { "source_path.$": "$.source.path", "destination_path.$": "$.destination.path", "recursive": true }
    ]
  },
  "ResultPath": "$.TransferResult",
  "WaitTime": 7200,
  "Next": "NextState"
}
```

## Legacy Transfer providers (deprecated)

`https://actions.globus.org/transfer/...` (transfer, ls, mkdir, delete, set_permission, ...) are deprecated, and `collection_info` there stopped being supported on 2025-01-22. When you see these in an existing flow, offer to migrate:

- Replace `https://actions.globus.org/transfer/` with `https://transfer.actions.globus.org/`.
- `set_permission` is now `manage_permission`.
- `transfer_items` became `DATA`; `source_endpoint_id` became `source_endpoint`; `destination_endpoint_id` became `destination_endpoint`. For delete, `items` became `DATA` and the elements need to be objects.
- Output fields changed too: `is_managed` was removed from collection info (check that `subscription_id` is non-null instead), and `is_folder` / `path_only` were removed from `ls` (use `stat` and its `type`).
- The new providers share the Transfer API scope, so users may need to re-consent after a flow is updated.

Full guide: https://docs.globus.org/api/transfer/action-providers/migration/

## Search

| ActionUrl | Purpose |
|---|---|
| `https://actions.globus.org/search/ingest` | Submit and monitor a Search ingest task. Scope `https://auth.globus.org/scopes/actions.globus.org/search/ingest` |
| `https://actions.globus.org/search/delete` | Delete-by-subject or delete-by-query task (confirm the exact URL on its docs page) |

Ingest parameters shown in the docs: `search_index` (UUID), `subject`, `content` (the metadata object), `visible_to` (list of principal URNs, for example a group URN).

```json
"Ingest": {
  "Type": "Action",
  "ActionUrl": "https://actions.globus.org/search/ingest",
  "Parameters": {
    "search_index.$": "$.search_index",
    "subject.$": "$.subject",
    "visible_to.$": "$.visible_to",
    "content.$": "$.metadata"
  },
  "ResultPath": "$.IngestResult",
  "Next": "NextState"
}
```

## Compute

Base `https://compute.actions.globus.org`. Two versions: V3 at `https://compute.actions.globus.org/v3` (preferred, more functionality) and V2 at the base URL. Both return results in the same format. The deprecated funcX provider (`automate.funcx.org`) should not be used.

V3 takes a `tasks` list, each with an endpoint ID, function ID, and `args`/`kwargs`; the endpoint ID is a JSON parameter, not part of the URL. Results are in `details.result` (list of outputs) and `details.results` (list of `{task_id, output}`).

```json
"Parameters": {
  "tasks": [
    {
      "endpoint.$": "$.compute_endpoint",
      "function.$": "$.function_id",
      "args.$": "$.args",
      "kwargs.$": "$.kwargs"
    }
  ]
}
```

The function must already be registered with Globus Compute, and the endpoint needs the required Python environment. Compute function definitions are separate work from the flow. Defining explicit args/kwargs is recommended.

Docs: https://globus-compute.readthedocs.io/en/stable/actionprovider.html

## Notification email

`https://actions.globus.org/notification/notify`. Takes `sender`, `destination`, `subject`, `body_template` with `${var}` placeholders, `body_variables`, `body_mimetype`, and `send_credentials` (SMTP or SES). Put `send_credentials` in `__Private_Parameters`. `destination.$: "$._context.email"` emails the runner.

## Wait for user selection

Hosted at `https://actions.globus.org/weboption/...`. Presents options (via unique URLs or a landing page) and the flow waits until someone selects one; the selection comes back as output a Choice state can branch on. A typical pattern: send a notification email with a link containing `$._context.run_id`, then wait for the response. Scope `https://auth.globus.org/scopes/5fac2e64-c734-4e6b-90ea-ff12ddbf9653/weboption_wait_for_option`.

## Expression evaluation

A hosted provider exists, but the docs state that expressions defined directly in Action `Parameters` or `ExpressionEval` states are preferred in most cases.

## Other

- Hello World: `https://actions.globus.org/hello_world`, a test provider.
- DataCite Mint: creates a DOI through DataCite.
- Registered APIs: any Globus-Auth-protected or unauthenticated HTTP API can be registered and then called from a flow. Use the Globus Registered API CLI.

## Custom action providers

When no hosted provider fits, build one with the Action Provider Tools (`pip install globus_action_provider_tools`). A provider needs a Globus Auth scope, an input schema, and the run/status/cancel/release interface. Then reference its URL as the `ActionUrl`.
