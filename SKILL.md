---
name: globus-flows-authoring
description: Author, review, validate, and deploy Globus Flows (flow definitions and input schemas). Covers the state language (Action, Choice, Wait, Pass, Fail, ExpressionEval), choosing and parameterizing Globus-hosted action providers (Transfer, Search, Compute, Notify, web input), expressions, Catch/error handling, RunAs, and input schemas for the Globus web app. Use this skill whenever the user mentions Globus Flows, a flow definition, flow JSON, action providers, ActionUrl, a flow input schema, "automate transfer then compute/ingest", Move or Two-Stage Transfer flows, or wants to chain Globus Transfer, Compute, or Search steps into one automated workflow, even if they never say "flow definition". Also use it to review or debug an existing flow definition.
---

# Globus Flows authoring

Purpose: turn a described workflow into a correct flow definition plus input schema, check it, and (with the user's go-ahead) deploy it. Flow definitions are JSON state machines extending Amazon States Language. Most authoring mistakes are small and mechanical (a missing `ResultPath`, a forgotten `.$`, an outdated `ActionUrl`), so the workflow below leans on a linter and on service-side validation instead of trusting a draft by eye.

| Need | Read |
|---|---|
| State types, Action fields, expressions, Catch, RunAs | `references/state-language.md` |
| Which action provider to use, its URL, and its parameters | `references/action-providers.md` |
| Input schemas, `globus-collection` format, `_context`, `_tokens` | `references/input-schemas.md` |
| Starting points for common shapes | `assets/templates/` |

Read the state-language reference before writing any non-trivial definition. Read the action-provider reference before choosing a `ActionUrl`, because several providers have been replaced and the new ones use different field names.

## Workflow

1. **Pin down the process before writing JSON.** Ask only for what is missing:
   - the ordered steps and what each one reads and produces
   - the systems touched (collections, a Search index, a Compute endpoint) and their UUIDs
   - what the person running the flow should be asked for (these become the input schema)
   - what should happen on failure of each step (stop, clean up, notify)
   - whether steps should run as the user or as the flow itself (`RunAs`), and whether anyone besides the author will run it
2. **Choose action providers.** Prefer Globus-hosted providers and, for Transfer, the current `transfer.actions.globus.org` family. Confirm input fields by introspection when you can reach the network (`curl <ActionUrl> | jq .input_schema`) or by checking the provider's docs page, rather than from memory. Action provider schemas change, and a wrong field name only surfaces at run time.
3. **Draft the definition and the input schema together.** Every `$.something` the definition reads must come from the input document or from an earlier `ResultPath`. Writing the schema alongside prevents references to inputs that nobody asked for.
4. **Lint locally:** `python scripts/lint_flow.py flow.json --input-schema schema.json`. Fix every error; read each warning and either fix it or be able to say why it is fine.
5. **Validate with the service** when the user has credentials (`FlowsClient.validate_flow`, see `scripts/validate_flow.py`). It checks structure and returns the scopes the flow needs, which tells you what consents the runner will be asked for. It cannot check expression results or detect infinite loops, so those still need a test run.
6. **Confirm before creating or updating a flow.** Creating a flow registers something others may run, and updating replaces the live definition. Show the user the final definition and who can view/run/administer it, then wait for a yes.
7. **Test with harmless data.** Suggest a first run against small or scratch collections. Report the run ID right away, then inspect the run's event log if it fails.

## Design rules and why they matter

- **Always set `ResultPath` on Action states.** The default is `$`, which replaces the entire run state with the action's output, wiping the inputs later states need. Use one named key per state (for example `$.TransferResult`).
- **Set `WaitTime` deliberately.** An Action state aborts the action after `WaitTime` seconds (default 300). Five minutes is too short for most real transfers and compute jobs, so pick a bound that fits the data volume. Also expect completion to be detected late: polling backs off up to 10 minutes.
- **Catch failures and keep the state intact.** Give every state that can reasonably fail a `Catch` for `ActionFailedException`, `ActionUnableToRun`, and `ActionTimeout` where relevant, and set the Catch `ResultPath` (for example `$.Error`) so the error does not overwrite the run state. End unrecoverable paths in a `Fail` state with an `Error` and `Cause`, so the run shows as failed instead of silently succeeding.
- **Use `.$` for references and `.=` for expressions.** A key like `"path": "$.source.path"` passes the literal string. It must be `"path.$": "$.source.path"`. The linter flags values that look like missed references.
- **Choice states read single values only.** To branch on a computed value, compute it first in an `ExpressionEval` state, then point the Choice `Variable` at the result. Always include a `Default`; with none and no matching rule the run errors out.
- **Never inline secrets.** If an action needs credentials (SMTP, SES), list the key in `__Private_Parameters` so it is hidden from run introspection. Where possible use `RunAs: "Flow"` and grant the flow's identity permissions instead of passing credentials.
- **Prefer `RunAs: "Flow"` over role tokens** when a step needs different privileges than the runner. Custom role names require the runner to pass tokens in `_tokens` and require the input schema to allow that property.
- **Make the input schema strict and friendly.** Use `additionalProperties: false`, `required`, titles and descriptions, and `format: "globus-collection"` for collection+path inputs so the web app renders a collection browser.
- **Keep definitions in version control** and treat the JSON file as the source of truth. Update the deployed flow from the file rather than editing in the web UI.

## Deploying

Use whichever the user already has set up. Do not print tokens.

- CLI: `globus flows create "TITLE" flow.json schema.json` and `globus flows update FLOW_ID --definition flow.json --input-schema schema.json`.
- Python: `FlowsClient.create_flow(title=..., definition=..., input_schema=...)`; starting a run uses `SpecificFlowClient(flow_id)`. For login, `UserApp`/`ClientApp` setup, and consent errors, follow the `globus-sdk` skill if it is available.
- A Globus Search/Transfer MCP server may be connected, but there is no Flows MCP tool here. Authoring and deployment go through files, the CLI, or the SDK.

## Scripts

Both take `--help`.

- `scripts/lint_flow.py`: offline, standard library only. Checks structure, transitions, reachability, Action field rules, deprecated URLs and old Transfer field names, `.$` mistakes, and (with `--input-schema`) references to inputs that do not exist. Exit code 1 on errors.
- `scripts/validate_flow.py`: calls the Flows validate endpoint with the SDK. Needs `pip install globus-sdk` and a login (set `GLOBUS_CLIENT_ID`). The SDK names it uses (`UserApp`, `FlowsClient(app=...)`, `validate_flow`, error attributes) were checked against globus-sdk 4.10, but the interactive login and the validate call have not been run against the live service, so treat the first use as a test and adjust if your SDK version differs.

## Templates

`assets/templates/` holds lint-clean starting points, each with a matching `.schema.json`. Adapt them rather than starting from a blank file when the shape fits:

- `transfer_and_ingest`: Transfer, then Search ingest, with Catch and Fail states.
- `stat_then_branch`: `stat` a path, then a Choice sends directories and single files down different Transfer states.

Both use the current Transfer providers. Check the field names against the provider's introspection output before relying on them.

## Reviewing an existing flow

Run the linter first, then read the definition for the things a linter cannot judge: a transfer followed by a delete with no check in between, a `WaitTime` far too short, steps that run as the user but need flow privileges, Choice rules that can never match, loops with no exit condition. Explain each finding in plain language with the specific fix.

## Output format

When presenting a result, give the definition and schema as separate JSON files or code blocks, then a short note covering the scopes or consents the runner will need, which parts are assumptions the user should confirm (UUIDs, paths, timeouts), and how to start a test run.
