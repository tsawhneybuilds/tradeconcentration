# Data Access Blocker

Created: 2026-05-17T22:28:51+00:00

The real-data exercises could not be run because the UN Comtrade API requires a valid subscription key for the HS6 bulk/final data needed here.

Reason:

No Comtrade subscription key found in COMTRADE_SUBSCRIPTION_KEY or --subscription-key.

What is needed:

1. Set a valid key in the shell:

   ```bash
   export COMTRADE_SUBSCRIPTION_KEY="..."
   ```

2. Re-run:

   ```bash
   python scripts/trade_concentration_pipeline.py --stage all
   ```

Policy followed:

- No synthetic or LLM-estimated trade values were used.
- WITS or other sources were not substituted for the required Comtrade reporter-product-partner HS6 records.
- `exercises.md` was not edited because no exercise results are ready for discussion.

Details:

```json
{
  "public_availability_file": "data/raw/comtrade/availability/prof_p_panel_public_availability.csv",
  "public_availability_rows_saved": 1130
}
```
