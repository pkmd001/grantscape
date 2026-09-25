#!/usr/bin/env python3
r"""
navigate_nih_funding.py  —  complete, self-contained workflow
=====================================================================
"Where does my science fit at NIH?"  A reproducible mapping of where a
research area is FUNDED, where its funded projects are REVIEWED, the
institute-wide funding ENVIRONMENT, and the area's MOMENTUM within the
NIH portfolio.

IMPORTANT — what this does and does not estimate
  This tool maps the landscape of *already-funded* work and reports
  *institute-wide* administrative success rates. It does NOT estimate an
  individual application's probability of funding: RePORTER contains
  funded projects only (no unsuccessful applications), and Data Book
  success rates are institute-wide across all investigator-initiated
  Type 1 applications, not specific to a topic within an institute.

Three public NIH resources:
  (1) RCDC categorical spending  -> report.nih.gov/funding/categorical-spending
        funding level, and momentum = a category's FY CAGR minus the
        median CAGR across RCDC categories (a descriptive benchmark; NIH
        does not budget by category, and categories overlap).
  (2) NIH RePORTER API           -> api.reporter.nih.gov
        funded R01s matching a keyword query, tallied by administering
        institute and study section. Full pagination. The AND/OR/Boolean
        operator is reported; an AND query that returns < MIN_HITS is
        re-run with OR and LOUDLY flagged.
  (3) NIH Data Book success rates by IC -> report.nih.gov/nihdatabook
        institute-wide new-application (Type 1) success rates.

INPUTS — two files to download once (RePORTER is queried live over the API):
  [RCDC spending]  Go to report.nih.gov/funding/categorical-spending -> download the
     "Estimates of Funding for Various Research, Condition, and Disease Categories
     (RCDC)" table (Excel or CSV). Save it, and set RCDC_PATH to its path. The loader
     auto-detects the header row and fiscal-year columns and ignores ARRA and
     mortality/prevalence columns, so a dated filename (e.g. RCDCFundingSummary_*.xlsx)
     works as-is.
  [IC success rates]  Two accepted forms:
     (a) One tidy CSV with columns  institute, fiscal_year, ic_success_rate  -> set
         ODDS_PATH to that .csv (simplest; e.g. the provided ic_success_rates.csv); or
     (b) The NIH Data Book per-IC exports (Report 157: new Type-1 RPG success rates),
         one .xlsx per Institute/Center, kept in one folder -> set ODDS_PATH to a glob
         like  NDB_Report_ID_157_exp_*.xlsx  and the script assembles them.
  Absolute paths are safest (they work regardless of the working directory).

Requires: requests, pandas, numpy (and openpyxl for .xlsx inputs).
Edit CONFIG (CONCEPT + the two paths) and run:  python navigate_nih_funding.py
=====================================================================
"""
import glob, re, time, json, collections, datetime
import requests
import pandas as pd
import numpy as np

# ============================ CONFIG =================================
CONCEPT        = "organ transplant"   # your research area (keywords)
OPERATOR       = "and"                 # "and" | "or" | "advanced"  (AND -> OR if sparse; see MIN_HITS)
RCDC_CATEGORY  = None                  # None = auto-match; or set an exact RCDC category name to override
FY_RANGE       = list(range(2015, 2024))   # RePORTER query window (2015..2023)
MOMENTUM_YEARS = (2015, 2024)          # RCDC CAGR window
ACTIVITY_CODES = ["R01"]
ODDS_YEAR      = 2025
MIN_FUNDING_M  = 50                    # floor ($M) for the momentum ranking, to drop tiny-base areas
MIN_HITS       = 30                    # AND -> OR fallback threshold
MAX_RECORDS    = 10000                 # RePORTER pagination cap (retrieves all if total <= cap)
RCDC_PATH      = r"RCDCFundingSummary*.xlsx"     # <- set to your downloaded RCDC table (see INPUTS above)
ODDS_PATH      = r"ic_success_rates.csv"         # <- tidy CSV, OR a glob of Data Book per-IC .xlsx (see INPUTS)
SAVE_CSVS      = True
SAVE_METADATA  = True
# ====================================================================

API = "https://api.reporter.nih.gov/v2/projects/search"

def _ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"

# ---------------- (1) RCDC categorical spending ----------------
_BURDEN = re.compile(r"mortalit|prevalence|death|cases|burden|arra|/\s*100|per\s*100|rate", re.I)

def _year(h):
    if _BURDEN.search(str(h)):
        return None
    m = re.fullmatch(r"\s*(20\d{2})\s*", str(h))
    return int(m.group(1)) if m else None

def _num(x):
    s = str(x).strip().replace(",", "").replace("$", "")
    if s in ("", "+", "-", "nan"):
        return np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan

def load_rcdc(path):
    import os
    if not os.path.exists(path):                 # tolerate date suffixes / globs
        hits = sorted(glob.glob(path)) or sorted(glob.glob(path.replace(".xlsx", "*.xlsx")))
        if not hits:
            raise FileNotFoundError(
                f"RCDC file not found: {path!r}. Set RCDC_PATH to the full path of your "
                f"downloaded 'Estimates of Funding ... (RCDC)' table.")
        path = hits[0]
    raw = (pd.read_excel(path, header=None)
           if str(path).lower().endswith((".xlsx", ".xls"))
           else pd.read_csv(path, header=None))
    hi = max(range(min(len(raw), 15)),
             key=lambda i: sum(_year(v) is not None for v in raw.iloc[i]))
    hdr = raw.iloc[hi].tolist()
    ycols = {_year(h): i for i, h in enumerate(hdr) if _year(h)}
    cat_i = next(i for i in range(len(hdr)) if i not in ycols.values())
    names, data = [], []
    for r in range(hi + 1, len(raw)):
        name = re.sub(r"\s*\d+\s*$", "", str(raw.iloc[r, cat_i]).strip())
        if not name or name == "nan":
            continue
        vals = {y: _num(raw.iloc[r, i]) for y, i in ycols.items()}
        if any(pd.notna(list(vals.values()))):
            names.append(name); data.append(vals)
    df = pd.DataFrame({"category": names})
    for y in sorted(ycols):
        df[y] = [d.get(y) for d in data]
    return df

def rcdc_momentum(df, y0, y1):
    """Momentum = each category's FY y0->y1 CAGR minus the median CAGR
    across RCDC categories. A descriptive benchmark, not a budget adjustment."""
    cagr = ((df[y1] / df[y0]) ** (1 / (y1 - y0)) - 1) * 100
    out = df[["category"]].copy()
    out["fy_latest"] = df[y1]
    out["cagr"] = cagr
    out["momentum"] = cagr - cagr.median()
    return out.sort_values("momentum", ascending=False)

def match_concept_to_rcdc(mom, concept, override=None):
    """Map the key-word query to an RCDC category and locate it in the momentum
    ranking. If `override` is given, that exact category is used. Otherwise a
    heuristic (stem-substring + fuzzy) picks the CLOSEST category -- this is an
    approximate, non-semantic match and should be verified (or overridden)."""
    import difflib
    m = mom.dropna(subset=["momentum"]).reset_index(drop=True)
    N = len(m)
    if override:
        hits = m.index[m["category"].str.lower() == override.lower()]
        if len(hits) == 0:
            return None
        rank = int(hits[0]) + 1
        pct = round(100 * (N - rank) / (N - 1)) if N > 1 else 0
        return m.iloc[hits[0]], rank, N, pct, True
    stems = [t[:6] for t in re.split(r"[^a-z]+", concept.lower()) if len(t) >= 4]
    m2 = m.assign(_score=m["category"].map(lambda c: sum(s in str(c).lower() for s in stems)))
    cand = m2[m2["_score"] > 0]
    if cand.empty:
        return None
    cand = cand.assign(_r=cand["category"].map(
        lambda c: difflib.SequenceMatcher(None, str(c).lower(), concept.lower()).ratio()))
    best = cand.sort_values(["_score", "_r"], ascending=False).iloc[0]
    rank = int(m.index[m["category"] == best["category"]][0]) + 1
    pct = round(100 * (N - rank) / (N - 1)) if N > 1 else 0
    return best, rank, N, pct, False

# ---------------- (2) RePORTER concept landscape ----------------
def _post(body, retries=4):
    for a in range(1, retries + 1):
        try:
            r = requests.post(API, json=body, timeout=90)
            r.raise_for_status()
            return r.json()
        except Exception:
            if a == retries:
                raise
            time.sleep(1.5 * a)

def _search(text, operator, offset):
    return _post({
        "criteria": {
            "advanced_text_search": {"operator": operator,
                "search_field": "projecttitle,abstracttext,terms", "search_text": text},
            "fiscal_years": FY_RANGE, "activity_codes": ACTIVITY_CODES, "agencies": ["NIH"]},
        "include_fields": ["FiscalYear", "AgencyIcAdmin", "FullStudySection"],
        "offset": offset, "limit": 500})

def concept_landscape(text, operator=OPERATOR):
    op_used = operator
    first = _search(text, op_used, 0)
    total = (first.get("meta") or {}).get("total", 0)
    if operator == "and" and total < MIN_HITS:
        op_used = "or"
        print(f"  !! WARNING: AND search for '{text}' returned {total} projects "
              f"(< MIN_HITS={MIN_HITS}); re-running with OR.")
        first = _search(text, op_used, 0)
        total = (first.get("meta") or {}).get("total", 0)
    recs = list(first.get("results") or [])
    off = 500
    while len(recs) < min(total, MAX_RECORDS):
        recs += _search(text, op_used, off).get("results") or []
        off += 500
        time.sleep(0.4)
    if len(recs) < total:
        print(f"  !! WARNING: retrieved {len(recs)} of {total} records "
              f"(MAX_RECORDS={MAX_RECORDS}); tallies are a truncated sample, "
              f"not the full population. Raise MAX_RECORDS to capture all.")
    def ic(r):
        a = r.get("agency_ic_admin")
        return (a or {}).get("abbreviation") if isinstance(a, dict) else a
    def ss(r):
        return (r.get("full_study_section") or {}).get("name")
    icc, ssc = collections.Counter(), collections.Counter()
    icy = collections.defaultdict(collections.Counter)
    ssy = collections.defaultdict(collections.Counter)
    for r in recs:
        i, s, y = ic(r), ss(r), r.get("fiscal_year")
        if i: icc[i] += 1; icy[i][y] += 1
        if s: ssc[s] += 1; ssy[s][y] += 1
    n = len(recs) or 1
    ic_df = pd.DataFrame([{"institute": i, "n_projects": c,
                           "pct": round(100 * c / n), "pct_exact": 100 * c / n,
                           **{f"FY{y}": icy[i].get(y, 0) for y in FY_RANGE}}
                          for i, c in icc.most_common()])
    ss_df = pd.DataFrame([{"study_section": s, "n_projects": c,
                           "pct": round(100 * c / n), "pct_exact": 100 * c / n,
                           **{f"FY{y}": ssy[s].get(y, 0) for y in FY_RANGE}}
                          for s, c in ssc.most_common()])
    return ic_df, ss_df, total, len(recs), op_used

# ---------------- (3) Data Book success rates ----------------
def _pct(x):
    try:
        v = float(x)
        return round(v * 100, 1) if v <= 1.5 else round(v, 1)
    except (TypeError, ValueError):
        return np.nan

def load_success_rates(path):
    files = glob.glob(path)
    xlsx = [f for f in files if f.lower().endswith((".xlsx", ".xls"))]
    if xlsx:  # assemble from per-IC Data Book exports
        rows = []
        for f in xlsx:
            raw = pd.read_excel(f, header=None)
            d = raw.iloc[5:, [0, 1, 2, 3]]
            d.columns = ["fy", "ic", "targeted", "untargeted"]
            d["fy"] = pd.to_numeric(d["fy"], errors="coerce")
            d = d.dropna(subset=["fy", "ic"])
            for _, r in d.iterrows():
                rows.append([str(r["ic"]).strip(), int(r["fy"]), _pct(r["untargeted"])])
        return pd.DataFrame(rows, columns=["institute", "fiscal_year", "ic_success_rate"]).drop_duplicates()
    return pd.read_csv(files[0] if files else path)

# ---------------- run ----------------
def main():
    run_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    mom = rcdc_momentum(load_rcdc(RCDC_PATH), *MOMENTUM_YEARS)
    ic_df, ss_df, total, got, op_used = concept_landscape(CONCEPT)
    sr = load_success_rates(ODDS_PATH)
    rate_col = "ic_success_rate" if "ic_success_rate" in sr.columns else sr.columns[-1]
    odds = sr[sr["fiscal_year"] == ODDS_YEAR].set_index("institute")[rate_col]
    ans = ic_df.head(6).copy()
    ans["ic_success_rate_%"] = ans["institute"].map(odds)

    print(f"\nCONCEPT: {CONCEPT}   (operator used: {op_used};  {got} of {total} funded R01s analyzed)\n")
    print("Where it is funded, and the institute-wide success rate:")
    print(ans[["institute", "pct", "ic_success_rate_%"]].to_string(index=False))
    print("\nStudy sections reviewing these funded projects:")
    print(ss_df.head(6)[["study_section", "pct"]].to_string(index=False))

    print("\nYour key-word area vs. NIH momentum:")
    match = match_concept_to_rcdc(mom, CONCEPT, override=RCDC_CATEGORY)
    if match:
        b, rank, N, pct, is_override = match
        label = "RCDC category (override)" if is_override else "Closest auto-matched RCDC category"
        direction = "faster than" if b["momentum"] > 0 else "slower than"
        print(f'  "{CONCEPT}"  ->  {label}: {b["category"]}')
        print(f'     CAGR {b["cagr"]:.1f}%/yr, momentum {b["momentum"]:+.1f} pp vs the median category '
              f'(rank {rank} of {N}; {_ordinal(pct)} percentile) -- growing {direction} the median NIH category.')
    else:
        print(f'  "{CONCEPT}" has no direct RCDC category match (set RCDC_CATEGORY to override).')
    print("\nFor comparison, the fastest-rising RCDC areas (CAGR minus median CAGR):")
    print(mom[mom["fy_latest"] >= MIN_FUNDING_M].head(8)[["category", "cagr", "momentum"]].round(1).to_string(index=False))

    if SAVE_CSVS:
        slug = re.sub(r"\W+", "_", CONCEPT.strip().lower())
        ic_df.to_csv(f"{slug}_by_ic.csv", index=False)
        ss_df.to_csv(f"{slug}_by_studysection.csv", index=False)
        mom.to_csv("rcdc_momentum.csv", index=False)
        print(f"\nWrote {slug}_by_ic.csv, {slug}_by_studysection.csv, rcdc_momentum.csv")

    if SAVE_METADATA:
        rcdc_map = match[0]["category"] if match else None
        meta = {"query": CONCEPT, "operator_requested": OPERATOR, "operator_used": op_used,
                "run_date_utc": run_date, "fiscal_years": [FY_RANGE[0], FY_RANGE[-1]],
                "activity_codes": ACTIVITY_CODES, "momentum_years": list(MOMENTUM_YEARS),
                "total_records": total, "retrieved_records": got,
                "truncated": got < total, "max_records": MAX_RECORDS,
                "rcdc_category_matched": rcdc_map, "rcdc_category_override": RCDC_CATEGORY,
                "odds_year": ODDS_YEAR, "api": API, "api_version": "RePORTER v2"}
        with open("run_metadata.json", "w") as fh:
            json.dump(meta, fh, indent=2)
        print("Wrote run_metadata.json")

if __name__ == "__main__":
    main()
