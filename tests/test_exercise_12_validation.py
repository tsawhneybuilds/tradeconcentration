from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from validate_exercise_12_outputs import (  # noqa: E402
    driver_category_schema_audit,
    reporter_alignment_audit,
)


class Exercise12ValidationTests(unittest.TestCase):
    def test_reporter_alignment_flags_scope_mismatch(self) -> None:
        core = pd.DataFrame({"reporter_code": [1, 2]})
        scope = pd.DataFrame({"reporter_code": [1]})

        audit = reporter_alignment_audit(core, core, core, scope, core)

        self.assertFalse(audit["reporter_sets_match_main"])
        self.assertEqual(audit["scope_missing_from_main_reporters"], [2])
        self.assertEqual(audit["scope_extra_vs_main_reporters"], [])

    def test_driver_category_schema_rejects_stale_new_item(self) -> None:
        main = pd.DataFrame({"driver_category": ["existing_top_10", "new_item"]})
        net = pd.DataFrame({"driver_category": ["existing_top_10", "strict_new_item"]})
        gross = pd.DataFrame({"driver_category": ["existing_top_10", "strict_new_item"]})

        audit = driver_category_schema_audit(main, net, gross)

        self.assertFalse(audit["driver_category_schema_valid"])
        self.assertEqual(audit["stale_new_item_rows"], 1)
        self.assertIn("new_item", audit["main_unexpected_driver_categories"])

    def test_driver_category_schema_accepts_strict_taxonomy(self) -> None:
        main = pd.DataFrame(
            {
                "driver_category": [
                    "existing_top_10",
                    "existing_non_top_10",
                    "strict_new_item",
                    "low_base_under_10k_grower",
                    "least_traded_10pct_grower",
                ]
            }
        )
        net = pd.DataFrame(
            {
                "driver_category": [
                    "existing_top_1pct",
                    "existing_non_top_5pct",
                    "strict_new_item",
                    "low_base_under_10k_grower",
                    "least_traded_10pct_grower",
                ]
            }
        )
        gross = pd.DataFrame(
            {
                "driver_category": [
                    "existing_top_10",
                    "exited_non_top_5pct",
                    "shrinking_top_1pct",
                    "strict_new_item",
                    "least_traded_10pct_grower",
                ]
            }
        )

        audit = driver_category_schema_audit(main, net, gross)

        self.assertTrue(audit["driver_category_schema_valid"])
        self.assertEqual(audit["stale_new_item_rows"], 0)


if __name__ == "__main__":
    unittest.main()
