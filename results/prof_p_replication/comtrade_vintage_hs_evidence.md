# Evidence on COMTRADE Vintage and HS-Code Handling

## Bottom Line

The paper states that the HS10 US data come from UC Davis CID and the HS6 33-country data come from UN COMTRADE. The appendix labels products as `H1-...`, so the paper most likely used HS1996/H1 data, not intentionally pure HS2002 data.

The remaining Table 2 product-count gap is still plausibly a data vintage / extraction-interface / HS-code-processing issue. The evidence is circumstantial but strong enough to justify asking for the original extract or query settings.

## Evidence

1. **The paper used UN COMTRADE for HS6.** In the local extracted paper text, the authors say the US HS10 data come from UC Davis and all remaining HS6 data come from UN COMTRADE.

2. **UN COMTRADE is revised over time.** A UN 2009 report says UNSD receives new and revised data for current and previous reporting years, and that revised data are a significant part of COMTRADE operations: https://unstats.un.org/unsd/trade/EG-IMTS/EG-IMTS%20197.9%20-%20UN%20Comtrade%20Data%20Availability%2C%20Data%20Revision%20and%20Usage.pdf

3. **UN says COMTRADE data are continuously added and revised.** The UNSD analytical trade tables page says the data are continuously updated and that UN COMTRADE data are continuously added and revised: https://unstats.un.org/unsd/trade/data/tables.asp

4. **UN tools can reflect refreshed/new-revised datasets.** The UN Comtrade Data Explorer page says data are regularly refreshed, taking into account incoming new/revised datasets: https://comtrade.un.org/labs/data-explorer/About.html

5. **HS classifications change, and conversion is not clean.** UNSD's classification note describes the H0/H1/H2 history and says it is not possible to properly convert an older HS revision to a newer revision in general: https://unstats.un.org/unsd/trade/dataextract/dataclass.htm

6. **WITS explicitly exposes different HS nomenclatures and an HS Combined option.** WITS documents H1/HS1996, H2/HS2002, and HS Combined, which lets users query across different reporting revisions: https://wits.worldbank.org/WITS/WITS/WITSHELP/Content/Basics/A5.Available_Nomenclatures.htm

7. **The WCO HS1996-to-HS2002 correlation has many one-to-many changes.** Our parsed WCO Table II contains 400 changed H1 codes and 897 mapping rows. These changes are enough to shift active product counts while barely moving Ginis: https://www.wcoomd.org/-/media/wco/public/global/pdf/topics/nomenclature/instruments-and-tools/hs-nomenclature-older-edition/2002/correlations-1996-2002/hs_correlation2002_table2_eng.pdf?la=en

8. **COMTRADE Plus changed residual-code conversion.** The Comtrade Plus methodology guide says older processing converted residual/non-standard commodity codes to HS `999999`, while the newer system maps residuals more specifically where possible before falling back to `999999`: https://comtrade.un.org/data/MethodologyGuideforComtradePlus.pdf

9. **Our local 2001 H1 files are not all one historical vintage.** The local bulk filenames for the paper sample contain publication dates ranging from 2002 to 2023, including Brazil 2001 H1 with a 2023 publication date and several European reporters with 2021-2022 publication dates. See `results/prof_p_replication/tables/local_2001_h1_comtrade_file_vintages.csv`.

## Interpretation

The safest wording is:

> The paper appears to use UN COMTRADE H1/HS1996, but the remaining Table 2 count discrepancy likely reflects differences between the original historical COMTRADE extract and our current COMTRADE bulk/Comtrade Plus-style files. Candidate mechanisms are revised country submissions, COMTRADE processing changes, residual-code handling, and HS revision/extraction-interface conventions. The WCO HS1996-to-HS2002 concordance diagnostic reproduces the direction and much of the magnitude of the count correction, but it is not proof that this exact rule was used in the paper.
