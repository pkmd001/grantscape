# Data-prep scripts

## pull_concept_landscape.py
Queries NIH RePORTER for funded projects matching abstract/title keywords and
tallies them by **Institute/Center** and **study section**, with yearly trends.
Edit the CONFIG block (keywords, fiscal years, mechanism), run it, then load
the two output CSVs into GrantScape's **Concept Landscape** tab.

Requirements: Python 3 with `requests` (and `certifi`), which handle HTTPS on
institutional networks. `pip install requests certifi` if needed.

Note: RePORTER contains funded projects only (no application denominator), so
the output is a funding/review landscape, not success rates.

## RCDC & Success-Rates data
These are direct public downloads (not scripted here) — see ../data/SOURCES.md.
