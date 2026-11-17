# globus-flows-authoring

A [Claude Code](https://claude.com/claude-code) skill for authoring, reviewing, validating, and deploying [Globus Flows](https://docs.globus.org/api/flows/): flow definitions and their input schemas.

It helps Claude with:

- the flow state language (Action, Choice, Wait, Pass, Fail, ExpressionEval), expressions, `Catch` handling, and `RunAs`
- choosing and parameterizing Globus-hosted action providers (Transfer, Search, Compute, Notify, web input)
- input schemas for the Globus web app (`globus-collection` format, `_context`, `_tokens`)
- linting and service-side validation of a draft before anything is deployed
- reviewing and debugging existing flow definitions

## Install

Clone the repository into your Claude Code skills directory:

```bash
git clone <repo-url> ~/.claude/skills/globus-flows-authoring
```

Claude Code picks the skill up automatically. It is used whenever you mention Globus Flows, flow definitions, action providers, or chaining Transfer, Compute, or Search steps.

## Layout

```
SKILL.md                    skill entry point: workflow and design rules
references/
  state-language.md         state types, Action fields, expressions, Catch, RunAs
  action-providers.md       provider URLs and parameters
  input-schemas.md          input schemas, globus-collection, _context, _tokens
scripts/
  lint_flow.py              offline linter (standard library only)
  validate_flow.py          service-side validation via globus-sdk
assets/templates/           lint-clean starting points with matching schemas
  transfer_and_ingest.*     Transfer, then Search ingest
  stat_then_branch.*        stat a path, then branch on file vs. directory
```

## Scripts

Both scripts accept `--help`.

Lint a flow offline (Python 3, no dependencies). Exits with code 1 on errors:

```bash
python scripts/lint_flow.py flow.json --input-schema schema.json
```

Validate a flow against the Flows service. This needs `pip install globus-sdk` and a login (set `GLOBUS_CLIENT_ID`):

```bash
python scripts/validate_flow.py --help
```

> **Note:** `validate_flow.py` was checked against the globus-sdk 4.10 API, but its interactive login and validate call have not been run against the live service. Treat the first use as a test.

## Safety

The skill is written so Claude confirms with you before creating or updating a deployed flow, and never prints tokens. Always test a new flow against small or scratch collections first.
