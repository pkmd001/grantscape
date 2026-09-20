# GrantScape

**The NIH funding landscape for grant strategy.** A single-page, dependency-free
web app that turns public NIH data into an applicant-facing view of *what NIH
funds*, *where the money is moving*, and *where a given line of science is
reviewed*. Runs entirely in the browser — no server, nothing uploaded.

> Companion tool to *[paper title / citation to be added]*.

## Why
NIH publishes the pieces — category funding (RCDC), success rates (Data Book),
and project-level review assignments (RePORTER) — but they live in separate
public silos, and the integrated portfolio-visualization tools NIH staff use
(PVIZ, iRePORT) are internal-only. GrantScape stitches the public pieces
together and adds derived metrics (budget-normalized momentum; concept →
institute/study-section mapping) that the public tools don't compute.

## Three tabs
1. **Funding Map** — load the RCDC categorical-spending CSV → funding level,
   share, and *momentum relative to the portfolio* (growth beyond the median
   category, removing the macro-budget trend), with per-category trend charts.
2. **Concept Landscape** — load the output of `scripts/pull_concept_landscape.py`
   → which **institutes** and **study sections** fund a keyword-defined area
   (funded volume + trend; funded projects only, not success rates).
3. **Institute Odds** — load an NIH success-rates-by-IC CSV → success rate and
   funding by institute; if the Concept Landscape institutes are loaded, odds
   are shown beside them (approximate, IC-level).

## Use
1. Open `index.html` (locally, or via GitHub Pages).
2. A real, dated NIH snapshot is bundled: `data/rcdc_categorical_spending_FY2008-2025.csv` — load it in the Funding Map tab. (Or click **Load synthetic demo** for a quick look.) Download the current table anytime from report.nih.gov.
3. Load your own CSVs per tab. See [`data/SOURCES.md`](data/SOURCES.md) for
   where to download the official tables and the expected formats.


- **Institute Odds** tab: a real snapshot is bundled — `data/ic_success_rates_1998-2025.csv` (NIH Data Book Report 157: new Type-1 RPG success rates by IC, 1998–2025; `success_rate` = investigator-initiated/untargeted). Load it and pick a fiscal year.


- **Concept Landscape** tab: worked-example CSVs bundled — `data/{transplant,regenmed}_by_ic.csv` and `..._by_studysection.csv` (from `pull_concept_landscape.py`, FY2015–23, R01). Load the by_ic and by_studysection pair for a concept.

## Hosting on GitHub Pages
Push this folder to a repo, enable Pages (Settings → Pages → deploy from
branch, root). `index.html` is fully static, so it works as-is. The concept
landscape uses pre-pulled CSVs (from the puller) because a static page cannot
query the RePORTER API directly.

## Repository layout
```
index.html                 the app (open this)
scripts/
  pull_concept_landscape.py generate the Concept Landscape CSVs from RePORTER
  README.md
data/
  SOURCES.md                where to get the official data + formats
  example_*_SYNTHETIC.csv    illustrative schemas (made-up numbers)
LICENSE                     MIT
```

## Caveats
RCDC categories overlap and NIH does not budget by category. IC success rates
are administrative and not topic-specific; study-section success rates are not
published anywhere. GrantScape is **descriptive** — a map to inform, not
determine, submission strategy — and its own companion study found that
converters tended to *continue* their research program rather than chase
trends. **Not affiliated with or endorsed by NIH.** All data are U.S.
government public-domain works.

## License
MIT — see [LICENSE](LICENSE).
