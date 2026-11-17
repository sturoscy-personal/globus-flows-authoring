# Flow definition state language

Source: https://docs.globus.org/api/flows/authoring-flows/ (verify details there when in doubt).

## Contents
- Top-level structure
- Run state and data referencing
- Action state
- Parameters: constants, references, expressions
- ExpressionEval, Pass, Choice, Wait, Fail
- Exceptions and Catch
- RunAs
- `$._context`
- Validation limits

## Top-level structure

A definition is a JSON object with `StartAt` (must match a key in `States`) and `States` (object of state name to state). `Comment` is allowed. Supported state types: `Action`, `ExpressionEval`, `Choice`, `Wait`, `Fail`, `Pass`. The docs also list `CreateWebInput` and `AwaitWebInput` for collecting human input; check the docs pages for their fields before using them.

Every state except `Choice` and `Fail` needs exactly one of `Next` or `End: true`. A `Choice` routes with its rules and `Default`. A `Fail` is terminal.

## Run state and data referencing

A run carries a JSON data payload that starts as the run's input and is passed from state to state. Each state writes its output into the payload at its `ResultPath`. References use JSONPath, always starting with `$.` (for example `$.source.path`, `$.TransferResult.details.task_id`).

## Action state

```json
{
  "Type": "Action",
  "ActionUrl": "https://transfer.actions.globus.org/transfer",
  "Parameters": { "...": "..." },
  "ResultPath": "$.TransferResult",
  "WaitTime": 7200,
  "ExceptionOnActionFailure": true,
  "RunAs": "User",
  "Catch": [
    { "ErrorEquals": ["ActionFailedException"], "ResultPath": "$.Error", "Next": "HandleFailure" }
  ],
  "Next": "NextState"
}
```

| Field | Notes |
|---|---|
| `ActionUrl` | Required. Base URL of the action provider. The flow service appends `/run`, `/status`, `/cancel`. |
| `Parameters` or `InputPath` | One is required; they are mutually exclusive. `Parameters` builds the body; `InputPath` uses an existing object in the run state as the body. |
| `ResultPath` | Where the action's full output goes. Default `$` overwrites the whole run state, so set it. Output includes `action_id`, `status`, `start_time`, `completion_time`, and `details` (the provider-specific result). |
| `WaitTime` | Max seconds to wait for completion. Default 300. The action is aborted if it is exceeded. Polling interval doubles up to 10 minutes. |
| `ExceptionOnActionFailure` | If true, a FAILED action raises `ActionFailedException`. If false, the FAILED status is written to `ResultPath` and the flow continues. |
| `RunAs` | `"User"` (default), `"Flow"`, or a custom role name. See RunAs below. |
| `Catch` | List of `{ErrorEquals, ResultPath?, Next}`. With no matching Catch, the run aborts. |
| `ActionScope` | Rarely needed; only for non-compliant providers that do not publish their scope. |
| `Next` / `End` | Exactly one. |

## Parameters

Values inside `Parameters` come in three forms:

- **Constant:** `"recursive": true`
- **Reference:** key ends in `.$`, value is a JSONPath. `"source_endpoint.$": "$.source.id"`
- **Expression:** key ends in `.=`, value is an expression string. `"label.=": "'Run ' + $._context.run_id"`

Nested objects and lists may themselves contain any of the three forms.

Hide sensitive values with `__Private_Parameters`, a list of keys in the same `Parameters` object:

```json
"Parameters": {
  "password": "...",
  "__Private_Parameters": ["password"]
}
```

## Expressions

Expression syntax resembles common languages: arithmetic on numbers, `+` for string and list concatenation, comparison and conditional (`x if cond else y`) forms. Functions documented include `is_present('path')` (existence check, avoids errors on undefined properties) and `getattr('x', default)`. References inside expressions are written as bare paths or backtick-quoted JSONPath depending on context; the docs show both `Path.To.Value` and `` `$.Path.To.Value` ``, so test any non-trivial expression in a real run, because validation cannot check them.

## ExpressionEval

An Action without the invocation: computes `Parameters` (with references and expressions) and stores them at `ResultPath`. `InputPath` is not allowed, so `Parameters` is required. Main use: compute a single value for a Choice to test.

```json
"ComputeFlag": {
  "Type": "ExpressionEval",
  "Parameters": { "has_files.=": "files_found > 0" },
  "ResultPath": "$.Flags",
  "Next": "Branch"
}
```

## Pass

Moves or reshapes run data with no action. Use `Parameters` and `ResultPath` (or `InputPath`) to copy data to a new location.

## Choice

```json
"Branch": {
  "Type": "Choice",
  "Choices": [
    { "Variable": "$.StatResult.details.type", "StringEquals": "dir", "Next": "TransferDirectory" }
  ],
  "Default": "TransferFile"
}
```

- Rules are evaluated in order; the first match wins.
- `Next` is required on top-level rules and not allowed on nested ones.
- Combine with `And`, `Or`, `Not` (each wraps nested rules).
- A Variable rule has `Variable` plus one comparison operator (such as `StringEquals`, `NumericGreaterThan`, `BooleanEquals`, `IsPresent`). Confirm the full operator list on the Choice docs page.
- No match and no `Default` means the run terminates with an error.
- Variable rules read a single value from the run state. Use ExpressionEval first for computed values.

## Wait

Pauses for a duration (`Seconds` or `SecondsPath`) or until a time (`Timestamp` or `TimestampPath`), following the States Language. Confirm field names on the Wait docs page before use.

## Fail

Terminates the run as failed. Fields: `Error` (short name) and `Cause` (explanation). Use it at the end of failure branches so the run is recorded as failed.

## Exceptions and Catch

Exception names documented: `ActionUnableToRun` (the action could not be started), `ActionFailedException` (the action ended FAILED, when `ExceptionOnActionFailure` is true), `ActionTimeout` (`WaitTime` exceeded). See https://docs.globus.org/api/flows/authoring-flows/exceptions/ for the complete list.

By default, error info overwrites the run state. Set the Catch `ResultPath` to keep the state:

```json
"Catch": [
  { "ErrorEquals": ["ActionUnableToRun"], "ResultPath": "$.FailureInfo", "Next": "HandleError" },
  { "ErrorEquals": ["ActionFailedException", "ActionTimeout"], "ResultPath": "$.FailureInfo", "Next": "HandleError" }
]
```

## RunAs

- `"User"` (default): the action runs with the runner's credentials.
- `"Flow"`: runs with the flow's own identity (its identity ID equals the flow ID). Grant that identity permissions on resources, and the flow becomes a controlled way to give limited access. This is the most common non-default use.
- Any other string is a role name. The runner must supply tokens under `_tokens.<RoleName>` in the flow input, the flow description lists the required scope per role in `globus_auth_scopes_by_RunAs`, and the input schema must permit `_tokens`.

## `$._context`

A read-only object with run metadata you can pass to action providers. Documented members that appear in the docs' examples: `$._context.run_id` and `$._context.email` (the runner's email). Check the context docs page for the full list.

## Validation limits

Service-side validation checks structure: required top-level and per-state fields, types, valid JSON paths. It cannot validate expression correctness (values are dynamic), changes made by expression evaluation, or infinite loops (a state cycling back to itself). Any flow with a loop needs an explicit exit condition and a test run.

For a loop, the pattern from Globus's trigger examples ("looping batched transfer and delete") is a Choice that routes back to an earlier state until a condition (for example, no more items listed) sends it onward.
