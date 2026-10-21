#!/usr/bin/env python3
"""Check which transit API a built React bundle targets before it is served.

NiceGUI serves frontend/dist under /calgary-transit-live/. A preview deployment
must not silently serve the tracked, production-targeted bundle, so a deployment
builds from source and runs this check against the API it expects:

  python ops/check_frontend_bundle.py --expect-api https://<preview-api-domain>/api

The bundle passes only if its transit-api-target.json (written by vite.config.js)
names exactly the expected API, and, for a non-production target, no JavaScript
asset mentions the production API. A bundle without the manifest (for example the
tracked dist/ built before M1) fails. Read-only; connects to nothing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIST = ROOT / "frontend" / "dist"
MANIFEST = "transit-api-target.json"
PRODUCTION_TRANSIT_API_BASE = "https://transit-api-production.up.railway.app/api"  # frontend/src/apiConfig.js


def check_bundle(dist: Path, expected_api: str) -> list[str]:
    """Problems found; an empty list means the bundle targets ``expected_api`` only."""
    expected = expected_api.rstrip("/")
    manifest = dist / MANIFEST
    if not manifest.is_file():
        return [f"{MANIFEST} missing: the bundle's API target is unknown; rebuild from source"]
    try:
        target = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [f"{MANIFEST} unreadable"]
    problems = []
    if not isinstance(target, dict) or target.get("api_base") != expected:
        problems.append(f"bundle targets {target.get('api_base') if isinstance(target, dict) else None!r}, "
                        f"expected {expected!r}")
    assets = sorted((dist / "assets").glob("*.js")) if (dist / "assets").is_dir() else []
    if not assets:
        problems.append("no JavaScript assets found")
    if expected != PRODUCTION_TRANSIT_API_BASE:
        mentioning = [a.name for a in assets if PRODUCTION_TRANSIT_API_BASE.encode() in a.read_bytes()]
        if mentioning:
            problems.append(f"production API referenced by {', '.join(mentioning)}")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--expect-api", required=True, help="the API base the bundle must target")
    parser.add_argument("--dist", type=Path, default=DEFAULT_DIST, help="built bundle directory")
    args = parser.parse_args(argv)
    problems = check_bundle(args.dist, args.expect_api)
    for problem in problems:
        print(f"FRONTEND BUNDLE REFUSED: {problem}", file=sys.stderr)
    if not problems:
        print(f"frontend bundle targets {args.expect_api.rstrip('/')}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
