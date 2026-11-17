#!/usr/bin/env python3
"""Validate a flow definition (and optional input schema) with the Globus Flows service.

Usage:
    export GLOBUS_CLIENT_ID=<your registered app's client ID>
    python validate_flow.py flow.json [--input-schema schema.json]

Needs `pip install globus-sdk` (a recent release that supports GlobusApp, i.e.
UserApp). Registers nothing: it only calls the validate endpoint, then prints
the scopes the flow needs. Register a client ID at
https://app.globus.org/settings/developers.

NOTE: written against the documented SDK API but not run against the live
service. Treat the first use as a test and adjust if your SDK version differs.
Tokens are never printed.
"""
import argparse
import json
import os
import sys


def load(path, label):
    try:
        with open(path) as fh:
            return json.load(fh)
    except FileNotFoundError:
        sys.exit(f"{label} file not found: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"{label} is not valid JSON ({path}): {e}")


def main():
    ap = argparse.ArgumentParser(description="Validate a flow with the Globus Flows service.")
    ap.add_argument("definition", help="path to the flow definition JSON")
    ap.add_argument("--input-schema", help="path to the input schema JSON")
    ap.add_argument("--client-id", default=os.environ.get("GLOBUS_CLIENT_ID"),
                    help="registered app client ID (default: $GLOBUS_CLIENT_ID)")
    args = ap.parse_args()

    if not args.client_id:
        sys.exit("No client ID. Set GLOBUS_CLIENT_ID or pass --client-id "
                 "(register one at https://app.globus.org/settings/developers).")

    try:
        import globus_sdk
    except ImportError:
        sys.exit("globus-sdk is not installed. Run: pip install globus-sdk")

    if not hasattr(globus_sdk, "UserApp"):
        sys.exit("This globus-sdk has no UserApp. Upgrade (pip install -U globus-sdk) "
                 "or adapt this script to your SDK's login flow.")

    definition = load(args.definition, "definition")
    kwargs = {"definition": definition}
    if args.input_schema:
        kwargs["input_schema"] = load(args.input_schema, "input schema")

    app = globus_sdk.UserApp("flow-authoring-validate", client_id=args.client_id)
    flows = globus_sdk.FlowsClient(app=app)

    try:
        resp = flows.validate_flow(**kwargs)
    except globus_sdk.GlobusAPIError as e:
        print(f"Validation failed (HTTP {e.http_status}, code {e.code}):")
        print(e.message)
        for sub in (e.errors or []):
            print(f"  - {sub.code}: {sub.message}")
        sys.exit(1)
    except globus_sdk.GlobusError as e:
        sys.exit(f"Could not reach or authenticate to the Flows service: {e}")

    print("Definition passed service-side validation.")
    scopes = resp.get("scopes", {})
    if scopes:
        print("\nScopes the flow will need (the runner is asked to consent to these):")
        for role, scope_list in scopes.items():
            print(f"  {role}:")
            for s in scope_list:
                print(f"    {s}")
    print("\nValidation does not check expression results or detect infinite loops; "
          "do a test run with small data.")


if __name__ == "__main__":
    main()
