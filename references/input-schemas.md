# Input schemas

Source: https://docs.globus.org/api/flows/input-schema/

An input schema is a JSON Schema document that the Flows service uses to validate the input a user supplies when starting a run. The Globus web app also renders it as a start form, so titles and descriptions are user-facing text.

## Baseline

```json
{
  "type": "object",
  "required": ["email_address"],
  "properties": {
    "email_address": {
      "type": "string",
      "format": "email",
      "title": "Email address",
      "description": "A welcome email will be sent to this address."
    }
  },
  "additionalProperties": false
}
```

Guidelines:
- Set `additionalProperties: false` at the top level and on nested objects so typos in input fail fast instead of being silently ignored.
- List everything the definition reads from the input under `required`, unless it has a default or the definition guards it with `is_present`/`getattr`.
- Every property the definition references as `$.name` should appear in `properties`. The linter cross-checks this with `--input-schema`.
- If the schema is omitted on create, the CLI default is an empty object `{}`, which accepts any object. Give real schemas for flows other people will run.

## Web app formats

The web app recognizes custom `format` values and renders richer controls:

**`globus-collection`** (type `object`): a collection picker with a path browser. The nested properties must be named `id` and `path`.

```json
"source": {
  "type": "object",
  "format": "globus-collection",
  "title": "Source collection and path",
  "required": ["id", "path"],
  "properties": {
    "id": { "type": "string", "format": "uuid" },
    "path": { "type": "string" }
  },
  "additionalProperties": false
}
```

In the definition this becomes `"source_endpoint.$": "$.source.id"` and `"source_path.$": "$.source.path"`. Mention to the user that the tutorial slides recommend collection paths that end in a slash for directories.

**`globus-principal`** (type `array`): a picker for identities and groups. The submitted value is a list of objects with `id`, `urn`, and `type` (`identity` or `group`). Documented as recommended for flows associated with collections.

**`globus-transfer-transfer#0.10`**: carries a Transfer settings object from the File Manager's guided start. Only relevant for flows associated with collection transfer actions (`associated_flow_policy`).

## Reserved input: `_tokens`

If any Action state uses a custom `RunAs` role name, the runner must pass tokens for it under `_tokens`, and the schema must allow it:

```json
"_tokens": {
  "type": "object",
  "required": ["Admin"],
  "properties": { "Admin": { "type": "string" } }
}
```

Without this the Flows service rejects the input before running. Prefer `RunAs: "Flow"` to avoid this entirely.

## Defaults and UX

- Use `default` for values most runs share (a standard destination collection, a recursive flag).
- Use `title` and `description` on every property. They are the form labels and help text.
- Use `enum` for closed choices, and `format: "uuid"` for IDs.
- Keep the input small. Derive anything you can inside the flow with `ExpressionEval` rather than asking the user for it.
