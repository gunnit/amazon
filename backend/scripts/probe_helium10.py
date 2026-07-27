"""Live probe for the Helium 10 integration — the go/no-go gate.

Run once real credentials exist (HELIUM10_API_KEY in the environment or
backend/.env). Verifies, field by field, what Helium 10 actually returns
for amazon.it ASINs before trusting the enrichment in production.

HELIUM10_API_KEY must be an OAuth 2.1 access token — Helium 10's MCP server
does not support API keys. To get one: connect `https://mcp.helium10.com/mcp`
in an MCP client that does the browser flow (Claude Code:
`claude mcp add helium10 --transport http https://mcp.helium10.com/mcp`),
authorize with a Diamond-plan Helium 10 account, then copy the issued access
token into the env var. Compare the printed payload against
``helium10._FIELD_KEYS`` and correct any key names that differ.

Usage:
    python scripts/probe_helium10.py B08XYZ1234 B07ABC5678 --marketplace IT
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import helium10  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("asins", nargs="+", help="ASINs to probe (use known amazon.it products)")
    parser.add_argument("--marketplace", default="IT")
    args = parser.parse_args()

    client = helium10.get_client()
    if client is None:
        print("HELIUM10_API_KEY is not set — nothing to probe.")
        return 1

    failures = 0
    for asin in args.asins:
        print(f"\n=== {asin} ({args.marketplace}) ===")
        payload = client.get_listing_details(asin, args.marketplace)
        if payload is None:
            print("NO RESPONSE (see warnings above)")
            failures += 1
            continue
        print("--- raw payload ---")
        print(json.dumps(payload, indent=2, default=str)[:4000])
        print("--- extracted metrics ---")
        metrics = helium10.extract_metrics(payload)
        for field in helium10._FIELD_KEYS:
            print(f"  {field}: {metrics.get(field, 'MISSING')}")
        if not metrics:
            failures += 1

    print(f"\n{len(args.asins) - failures}/{len(args.asins)} ASINs returned usable metrics")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
