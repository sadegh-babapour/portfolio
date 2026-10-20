"""ops/check_frontend_bundle.py against synthetic bundles: a deployment must serve
only a bundle built for the API it expects, never a silent production fallback."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ops import check_frontend_bundle as check

PREVIEW = "https://transit-api-preview.example/api"
PRODUCTION = check.PRODUCTION_TRANSIT_API_BASE


def bundle(root: str, *, api_base=None, asset_text="fetch(API)") -> Path:
    dist = Path(root, "dist")
    (dist / "assets").mkdir(parents=True)
    (dist / "assets" / "main-abc.js").write_text(asset_text)
    if api_base is not None:
        (dist / check.MANIFEST).write_text(json.dumps({"mode": "preview", "api_base": api_base}))
    return dist


class FrontendBundleTests(unittest.TestCase):
    def test_matching_preview_bundle_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(check.check_bundle(bundle(tmp, api_base=PREVIEW, asset_text=PREVIEW), PREVIEW + "/"), [])

    def test_unverifiable_or_mismatched_bundles_fail(self):
        cases = {
            "no manifest (tracked pre-M1 dist)": dict(api_base=None),
            "production manifest": dict(api_base=PRODUCTION),
            "production URL in an asset": dict(api_base=PREVIEW, asset_text=f"const a='{PRODUCTION}'"),
        }
        for name, options in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                self.assertNotEqual(check.check_bundle(bundle(tmp, **options), PREVIEW), [])

    def test_constant_matches_the_frontend_source(self):
        source = (check.ROOT / "frontend" / "src" / "apiConfig.js").read_text(encoding="utf-8")
        self.assertIn(f'"{PRODUCTION}"', source)


if __name__ == "__main__":
    unittest.main()
