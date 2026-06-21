from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_fixed_universe_gini_site as site


class FixedUniverseGiniSiteTests(unittest.TestCase):
    def test_site_data_contract_is_rd2_harmonized_and_compact(self) -> None:
        data = site.load_site_data()
        self.assertEqual(data["country_sample"], "rd2_countries")
        self.assertEqual(data["benchmark_sample"], "world_broad")
        self.assertEqual(data["product_id_mode"], "harmonized_hs6_family")
        self.assertEqual(set(data["years"]), {"Exports", "Imports"})
        self.assertLess(len(data["panel"]), 4000)
        for flow in ["Exports", "Imports"]:
            self.assertEqual(data["universe_counts"][flow], 5037)

    def test_write_site_creates_pages_assets_and_downloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            manifest = site.write_site(output)
            self.assertEqual(manifest["country_sample"], "rd2_countries")
            for rel_path in [
                "index.html",
                "methods.html",
                "downloads.html",
                "assets/site-data.json",
                "assets/site-data.js",
                "assets/site-manifest.json",
                "assets/app.js",
                "assets/styles.css",
            ]:
                self.assertTrue((output / rel_path).exists(), rel_path)
            self.assertIn("fixed_universe_product_gini_all_years.csv", manifest["downloads"])
            data = json.loads((output / "assets/site-data.json").read_text(encoding="utf-8"))
            self.assertTrue(data["panel"])
            checked = "\n".join(
                (output / rel_path).read_text(encoding="utf-8")
                for rel_path in ["index.html", "methods.html", "downloads.html", "assets/site-data.js"]
            )
            self.assertNotIn("NaN", checked)
            self.assertNotIn("undefined", checked)


if __name__ == "__main__":
    unittest.main()
