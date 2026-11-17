#!/usr/bin/env python3
"""Offline linter for Globus Flows definitions (standard library only).

Usage:
    python lint_flow.py flow.json [--input-schema schema.json]

Checks structure, transitions, reachability, Action field rules, deprecated
action provider URLs, common `.$` mistakes, and (optionally) that `$.x`
references point at something the input schema or an earlier ResultPath
provides. It is a heuristic aid and does not replace service-side validation
or a test run. Exit status is 1 if any error is found, else 0.
"""
import argparse
import json
import re
import sys

KNOWN_TYPES = {
    "Action", "ExpressionEval", "Choice", "Wait", "Fail", "Pass",
    "CreateWebInput", "AwaitWebInput",
}
TERMINAL_TYPES = {"Fail"}
OLD_TRANSFER_PREFIX = "https://actions.globus.org/transfer/"
NEW_TRANSFER_PREFIX = "https://transfer.actions.globus.org/"
OLD_TRANSFER_FIELDS = {"transfer_items", "source_endpoint_id", "destination_endpoint_id", "items"}
LONG_RUNNING_HINTS = ("/transfer", "/delete", "compute.actions.globus.org", "search/ingest")
RESERVED_ROOTS = {"_context", "_tokens"}


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def error(self, where, msg):
        self.errors.append(f"ERROR   {where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"WARNING {where}: {msg}")


def root_key(path):
    """First key of a JSONPath like $.a.b[0] -> 'a'. Returns None if not parseable."""
    m = re.match(r"^\$\.([A-Za-z0-9_\-]+)", path)
    return m.group(1) if m else None


def walk_params(obj, where, rep, refs, prefix=""):
    """Inspect a Parameters object, collecting `.$` references and flagging mistakes."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            loc = f"{where}.Parameters{prefix}.{k}"
            if k.endswith(".$"):
                if not isinstance(v, str) or not v.startswith("$"):
                    rep.error(loc, "a '.$' key must have a JSONPath string starting with '$'")
                else:
                    refs.append((loc, v))
            elif k.endswith(".="):
                if not isinstance(v, str):
                    rep.error(loc, "a '.=' key must have an expression string")
                else:
                    for m in re.finditer(r"`(\$\.[^`]+)`", v):
                        refs.append((loc, m.group(1)))
            elif isinstance(v, str) and v.startswith("$.") and k != "__COMMENT":
                rep.warn(loc, f"value {v!r} looks like a reference but key lacks '.$' "
                              f"(it would be passed as a literal string; use '{k}.$')")
            if isinstance(v, (dict, list)):
                walk_params(v, where, rep, refs, prefix=f"{prefix}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk_params(v, where, rep, refs, prefix=f"{prefix}[{i}]")


def successors(state):
    nxt = []
    if "Next" in state:
        nxt.append(state["Next"])
    for rule in state.get("Choices", []) or []:
        if isinstance(rule, dict) and "Next" in rule:
            nxt.append(rule["Next"])
    if "Default" in state:
        nxt.append(state["Default"])
    for c in state.get("Catch", []) or []:
        if isinstance(c, dict) and "Next" in c:
            nxt.append(c["Next"])
    return nxt


def is_terminal(state):
    return state.get("End") is True or state.get("Type") in TERMINAL_TYPES


def lint(defn, schema, rep):
    if not isinstance(defn, dict):
        rep.error("definition", "must be a JSON object")
        return
    states = defn.get("States")
    start = defn.get("StartAt")
    if not isinstance(states, dict) or not states:
        rep.error("definition", "'States' must be a non-empty object")
        return
    if not isinstance(start, str):
        rep.error("definition", "'StartAt' is required and must be a string")
    elif start not in states:
        rep.error("definition", f"'StartAt' names {start!r}, which is not in States")

    # Names available to $.x references: input schema properties + all ResultPath roots.
    provided = set(RESERVED_ROOTS)
    schema_props = set()
    if schema is not None:
        schema_props = set((schema.get("properties") or {}).keys())
        provided |= schema_props
    result_roots = set()
    for st in states.values():
        if isinstance(st, dict):
            rp = st.get("ResultPath")
            if isinstance(rp, str) and rp != "$":
                r = root_key(rp)
                if r:
                    result_roots.add(r)
            for c in st.get("Catch", []) or []:
                if isinstance(c, dict) and isinstance(c.get("ResultPath"), str):
                    r = root_key(c["ResultPath"])
                    if r:
                        result_roots.add(r)
    provided |= result_roots

    all_refs = []
    for name, st in states.items():
        where = f"state {name!r}"
        if not isinstance(st, dict):
            rep.error(where, "state must be an object")
            continue
        t = st.get("Type")
        if t not in KNOWN_TYPES:
            rep.error(where, f"unknown or missing Type {t!r} (expected one of {sorted(KNOWN_TYPES)})")
            continue

        # Transition rules
        if t not in ("Choice", "Fail"):
            has_next, has_end = "Next" in st, st.get("End") is True
            if has_next and has_end:
                rep.error(where, "has both 'Next' and 'End'; use exactly one")
            elif not has_next and not has_end:
                rep.error(where, "needs 'Next' or 'End': true")
        if t == "Fail" and ("Next" in st or "End" in st):
            rep.warn(where, "Fail is terminal; 'Next'/'End' are ignored or invalid")
        for target in successors(st):
            if target not in states:
                rep.error(where, f"transition to {target!r}, which is not a defined state")

        # Parameters / references
        params = st.get("Parameters")
        if isinstance(params, dict):
            walk_params(params, where, rep, all_refs)
            priv = params.get("__Private_Parameters")
            if isinstance(priv, list):
                for p in priv:
                    if p not in params:
                        rep.warn(where, f"__Private_Parameters lists {p!r}, which is not a key in Parameters")
        for key in ("InputPath", "ResultPath"):
            v = st.get(key)
            if isinstance(v, str) and not v.startswith("$"):
                rep.error(where, f"{key} must be a JSONPath starting with '$'")
            elif isinstance(v, str) and key == "InputPath":
                all_refs.append((f"{where}.InputPath", v))

        if t == "Action":
            url = st.get("ActionUrl")
            if not isinstance(url, str) or not url:
                rep.error(where, "Action requires 'ActionUrl'")
                url = ""
            if "Parameters" in st and "InputPath" in st:
                rep.error(where, "'Parameters' and 'InputPath' are mutually exclusive")
            elif "Parameters" not in st and "InputPath" not in st:
                rep.error(where, "Action requires either 'Parameters' or 'InputPath'")
            if "ResultPath" not in st:
                rep.warn(where, "no ResultPath: the action's output will replace the entire run state ('$'). "
                                "Set e.g. \"ResultPath\": \"$." + name + "Result\"")
            elif st.get("ResultPath") == "$":
                rep.warn(where, "ResultPath '$' overwrites the entire run state")
            if "WaitTime" not in st and any(h in url for h in LONG_RUNNING_HINTS):
                rep.warn(where, "no WaitTime on a likely long-running action; the default is 300 seconds "
                                "and the action is aborted after that")
            if url.startswith(OLD_TRANSFER_PREFIX):
                rep.warn(where, "deprecated Transfer action provider URL; migrate to "
                                f"{NEW_TRANSFER_PREFIX}<action> (see transfer action provider migration guide)")
            if url.startswith(NEW_TRANSFER_PREFIX) and isinstance(params, dict):
                old = sorted(OLD_TRANSFER_FIELDS & {k.rstrip("$.=").rstrip(".") for k in params})
                if old:
                    rep.error(where, f"old-style Transfer field(s) {old} used with the new Transfer "
                                     "provider; new names are DATA, source_endpoint, destination_endpoint")
            if "Catch" not in st and "End" not in st and url:
                rep.warn(where, "no Catch: any action failure or timeout aborts the run")
            if st.get("RunAs") not in (None, "User", "Flow"):
                rep.warn(where, f"RunAs {st.get('RunAs')!r} is a custom role: the runner must pass "
                                f"_tokens.{st.get('RunAs')} and the input schema must allow '_tokens'")

        if t == "ExpressionEval":
            if "InputPath" in st:
                rep.error(where, "ExpressionEval cannot use InputPath")
            if "Parameters" not in st:
                rep.error(where, "ExpressionEval requires 'Parameters'")

        if t == "Choice":
            choices = st.get("Choices")
            if not isinstance(choices, list) or not choices:
                rep.error(where, "Choice requires a non-empty 'Choices' list")
            else:
                for i, rule in enumerate(choices):
                    if not isinstance(rule, dict):
                        rep.error(where, f"Choices[{i}] must be an object")
                        continue
                    if "Next" not in rule:
                        rep.error(where, f"Choices[{i}] is missing 'Next' (required on top-level rules)")
                    var = rule.get("Variable")
                    if isinstance(var, str):
                        all_refs.append((f"{where}.Choices[{i}].Variable", var))
            if "Default" not in st:
                rep.warn(where, "no 'Default': if no rule matches, the run terminates with an error")

        if t == "Fail" and "Error" not in st:
            rep.warn(where, "Fail without 'Error'; add 'Error' and 'Cause' so the failure is explained in the run")

        for i, c in enumerate(st.get("Catch", []) or []):
            if not isinstance(c, dict) or "ErrorEquals" not in c or "Next" not in c:
                rep.error(where, f"Catch[{i}] needs 'ErrorEquals' and 'Next'")
            elif "ResultPath" not in c:
                rep.warn(where, f"Catch[{i}] has no ResultPath: error info will overwrite the run state")

    # Reference check
    if schema is not None or result_roots:
        for loc, path in all_refs:
            r = root_key(path)
            if r is None or r in provided:
                continue
            if schema is None:
                continue  # without a schema we cannot tell what inputs exist
            rep.warn(loc, f"reference {path!r} uses root '{r}', which is neither an input-schema property "
                          "nor produced by any ResultPath")

    # Reachability and loop-exit checks
    if isinstance(start, str) and start in states:
        seen, stack = set(), [start]
        while stack:
            cur = stack.pop()
            if cur in seen or cur not in states or not isinstance(states[cur], dict):
                continue
            seen.add(cur)
            stack.extend(successors(states[cur]))
        for name in states:
            if name not in seen:
                rep.warn(f"state {name!r}", "unreachable from StartAt")

        # Every reachable state should be able to reach a terminal state (else: possible infinite loop).
        can_finish = {n for n in seen if isinstance(states[n], dict) and is_terminal(states[n])}
        changed = True
        while changed:
            changed = False
            for n in seen:
                if n in can_finish or not isinstance(states[n], dict):
                    continue
                if any(s in can_finish for s in successors(states[n])):
                    can_finish.add(n)
                    changed = True
        for n in sorted(seen - can_finish):
            rep.error(f"state {n!r}", "cannot reach any End/Fail state (infinite loop?). "
                                      "Service validation does not detect loops, so give every cycle an exit")
        if not any(isinstance(states[n], dict) and is_terminal(states[n]) for n in seen):
            rep.error("definition", "no reachable state ends the flow (needs End: true or a Fail state)")


def load(path, label):
    try:
        with open(path) as fh:
            return json.load(fh)
    except FileNotFoundError:
        sys.exit(f"{label} file not found: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"{label} is not valid JSON ({path}): {e}")


def main():
    ap = argparse.ArgumentParser(description="Lint a Globus Flows definition.")
    ap.add_argument("definition", help="path to the flow definition JSON")
    ap.add_argument("--input-schema", help="path to the input schema JSON (enables reference checks)")
    args = ap.parse_args()

    defn = load(args.definition, "definition")
    schema = load(args.input_schema, "input schema") if args.input_schema else None
    rep = Report()
    lint(defn, schema, rep)

    for line in rep.errors + rep.warnings:
        print(line)
    n_states = len(defn.get("States", {})) if isinstance(defn, dict) and isinstance(defn.get("States"), dict) else 0
    print(f"\n{n_states} state(s) checked: {len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
    sys.exit(1 if rep.errors else 0)


if __name__ == "__main__":
    main()
