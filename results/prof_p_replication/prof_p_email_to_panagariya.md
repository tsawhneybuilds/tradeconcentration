Subject: 2001 COMTRADE HS6 replication check

Dear Professor Panagariya,

I investigated the 2001 UN COMTRADE HS6 replication for the paper's 33-country sample. The main result is that the product concentration results are very close, while the remaining partner-concentration discrepancies are concentrated in a few rows and appear to depend on how the old COMTRADE/WITS extract treated aggregate partners.

For Table 2, the product Ginis are already very close before any HS harmonization: the mean absolute Gini difference is 0.0028 for exports and 0.0038 for imports, with maximum differences of 0.0117 and 0.0159. The India/China ordering also matches the paper: India is more concentrated than China for both exports and imports. The larger mismatch is product counts, not Ginis. A WCO HS1996-to-HS2002 concordance diagnostic reduces the mean absolute product-count gap from about 132 products to 45, while leaving the Ginis close.

For Tables 3 and 4, most top-five partner shares match closely, but six rows remain large outliers: Greece, India, and Finland for export destinations, and Turkey, Switzerland, and Slovakia for import sources. Using the COMTRADE `World` row as the denominator is fine and is now the default diagnostic, but it does not resolve those six rows because the World total equals the sum of actual partner countries almost exactly. The six rows become close only if `World` is counted as one of the top-five partners, which would double-count trade and is not a clean partner-concentration measure. I also tested HS harmonization for these partner results; any value-preserving HS mapping leaves partner totals unchanged, so it cannot explain the discrepancy.

Attached are two short notes: one summarizes the replication findings and diagnostics, and the other is a step-by-step processing cookbook. Do you happen to still have the original COMTRADE/WITS extract, Stata code, CSV files, or query notes used for the HS6 tables? Even a saved data file or a note on whether the data were pulled through WITS versus the old UN COMTRADE interface would let me pin down whether these six rows reflect an intended convention or an extraction artifact.

Best regards,
[Your Name]
