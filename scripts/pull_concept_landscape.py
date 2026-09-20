r"""
pull_concept_landscape.py
=====================================================================
Concept-anchored funding landscape by INSTITUTE and STUDY SECTION.

Given abstract/title keywords, a period, and a mechanism, this finds the
NIH-funded projects matching that concept and tallies:
  * which Institutes/Centers (ICs) fund the area (volume + yearly trend)
  * which study sections review/fund it (volume + yearly trend)
so an applicant can see where their kind of science actually lands.

Concept source: RePORTER advanced text search over title + abstract +
terms (the only place that ties concept text to IC and study section on
the same funded projects). Institute success-rate tables carry no
concept content, so odds are joined on afterward, at the IC level, as an
APPROXIMATION (see ODDS below).

IMPORTANT INTERPRETATION
  RePORTER contains FUNDED projects only, not applications. These tallies
  are therefore "where funded work in this area lands," not success
  rates. Study-section success rates are not publicly available at all.
  IC-level R01 success rates (optional join) are administrative and NOT
  specific to your topic within that IC \u2014 treat the odds column as a
  coarse guide, not a per-topic probability.

Run in PyCharm. No arguments. Edit CONFIG.
Outputs: concept_landscape_by_ic.csv, concept_landscape_by_studysection.csv
=====================================================================
"""
import csv, json, time, collections
from pathlib import Path

# ============================ CONFIG =================================
SEARCH_TEXT   = "single cell RNA sequencing"     # your concept keywords
OPERATOR      = "and"        # "and" (all words), "or" (any), or "advanced"
FISCAL_YEARS  = list(range(2015, 2024))          # period to characterize
ACTIVITY_CODES= ["R01", "R37"]                   # mechanism(s)
OUT_DIR       = Path(r"C:\Users\pkmd0\Downloads")
# Optional: NIH "Success Rates by Institute/Center" CSV to add an odds column.
# Leave "" to skip. Download from report.nih.gov (Success Rates).
SUCCESS_RATE_CSV = ""

MAX_RECORDS = 5000           # safety cap on matched projects
PAGE = 500; REQUEST_PAUSE = 0.8; MAX_RETRIES = 4
# ====================================================================

API="https://api.reporter.nih.gov/v2/projects/search"
INCLUDE=["ApplId","FiscalYear","AgencyIcAdmin","StudySection","FullStudySection",
         "ProjectTitle","ActivityCode"]
_MODE=None; _SESSION=None
try:
    import requests
    _SESSION=requests.Session(); _SESSION.headers.update({"Content-Type":"application/json","User-Agent":"k2r-landscape/1.0"}); _MODE="requests"
except Exception:
    import urllib.request, ssl
    try:
        import certifi; _CTX=ssl.create_default_context(cafile=certifi.where()); _MODE="urllib+certifi"
    except Exception:
        _CTX=ssl.create_default_context(); _MODE="urllib"

def _post(body):
    data=json.dumps(body).encode()
    if _MODE=="requests":
        r=_SESSION.post(API,data=data,timeout=90); r.raise_for_status(); return r.json()
    import urllib.request
    req=urllib.request.Request(API,data=data,headers={"Content-Type":"application/json","User-Agent":"k2r-landscape/1.0"})
    with urllib.request.urlopen(req,timeout=90,context=_CTX) as resp:
        return json.loads(resp.read().decode())

def search(offset, verbose=False):
    body={"criteria":{
            "advanced_text_search":{"operator":OPERATOR,
                "search_field":"projecttitle,abstracttext,terms","search_text":SEARCH_TEXT},
            "fiscal_years":[int(y) for y in FISCAL_YEARS],
            "activity_codes":ACTIVITY_CODES,
            "agencies":["NIH"]},
          "include_fields":INCLUDE,"offset":offset,"limit":PAGE}
    for a in range(1,MAX_RETRIES+1):
        try:
            j=_post(body)
            if verbose:
                print("    [diag] meta.total=",(j.get("meta") or {}).get("total"))
                if j.get("results"): print("    [diag] record keys:",sorted(j["results"][0].keys()))
            return j
        except Exception as e:
            if a==MAX_RETRIES: raise
            time.sleep(1.5*a)

def ic_of(rec):
    a=rec.get("agency_ic_admin")
    if isinstance(a,dict): return a.get("abbreviation") or a.get("code") or a.get("name") or ""
    return a or rec.get("agency_ic_admin_abbreviation") or ""

def ss_of(rec):
    f=rec.get("full_study_section")
    if isinstance(f,dict) and f.get("name"): return f["name"]
    return rec.get("study_section_name") or rec.get("study_section") or "(not assigned)"

def main():
    print(f"HTTP transport: {_MODE}")
    print(f"Concept: '{SEARCH_TEXT}' [{OPERATOR}]  FY {FISCAL_YEARS[0]}-{FISCAL_YEARS[-1]}  mech {ACTIVITY_CODES}\n")
    # paginate matched projects
    first=search(0,verbose=True); total=(first.get("meta") or {}).get("total",0)
    print(f"Matched funded projects: {total}")
    if total==0:
        print("No matches \u2014 try OPERATOR='or', broader keywords, or wider years."); return
    recs=list(first.get("results") or [])
    got=len(recs); off=PAGE
    while got<min(total,MAX_RECORDS):
        recs+= (search(off).get("results") or []); off+=PAGE; got=len(recs)
        print(f"  fetched {got}/{min(total,MAX_RECORDS)}"); time.sleep(REQUEST_PAUSE)
    if total>MAX_RECORDS: print(f"  ** capped at {MAX_RECORDS} of {total}; tallies are a sample. **")

    ic=collections.Counter(); ss=collections.Counter()
    ic_yr=collections.defaultdict(collections.Counter); ss_yr=collections.defaultdict(collections.Counter)
    for r in recs:
        y=r.get("fiscal_year"); i=ic_of(r); s=ss_of(r)
        if i: ic[i]+=1; ic_yr[i][y]+=1
        if s: ss[s]+=1; ss_yr[s][y]+=1
    n=len(recs)

    # optional IC odds join
    odds={}
    if SUCCESS_RATE_CSV and Path(SUCCESS_RATE_CSV).exists():
        with open(SUCCESS_RATE_CSV,newline="",encoding="utf-8-sig") as fh:
            rows=list(csv.reader(fh))
        # flexible: find a column with IC abbrev and one with a success rate (0-100 or 0-1)
        hdr=None
        for row in rows[:10]:
            if any("success" in c.lower() for c in row): hdr=row; hi=rows.index(row); break
        if hdr:
            ic_col=next((k for k,c in enumerate(hdr) if any(t in c.lower() for t in("institute","ic","center","abbrev"))),0)
            sr_col=next((k for k,c in enumerate(hdr) if "success" in c.lower()),None)
            for row in rows[hi+1:]:
                if sr_col is not None and len(row)>max(ic_col,sr_col):
                    try: odds[row[ic_col].strip().upper()]=float(row[sr_col].replace("%","").strip())
                    except Exception: pass
            print(f"Joined IC success rates for {len(odds)} ICs from {SUCCESS_RATE_CSV}")

    yrs=FISCAL_YEARS
    def trend(cyr): return " ".join(str(cyr.get(y,0)) for y in yrs)
    # write IC landscape
    p1=OUT_DIR/"concept_landscape_by_ic.csv"
    with p1.open("w",newline="",encoding="utf-8-sig") as fh:
        w=csv.writer(fh)
        head=["institute","n_projects","pct_of_matched"]+(["ic_R01_success_rate*"] if odds else [])+[f"FY{y}" for y in yrs]
        w.writerow(head)
        for i,c in ic.most_common():
            row=[i,c,round(100*c/n,1)]+([odds.get(i.upper(),"")] if odds else [])+[ic_yr[i].get(y,0) for y in yrs]
            w.writerow(row)
    # write study-section landscape
    p2=OUT_DIR/"concept_landscape_by_studysection.csv"
    with p2.open("w",newline="",encoding="utf-8-sig") as fh:
        w=csv.writer(fh)
        w.writerow(["study_section","n_projects","pct_of_matched"]+[f"FY{y}" for y in yrs])
        for s,c in ss.most_common():
            w.writerow([s,c,round(100*c/n,1)]+[ss_yr[s].get(y,0) for y in yrs])

    print(f"\nTop institutes for this concept:")
    for i,c in ic.most_common(8):
        o=f"  (IC R01 success ~{odds.get(i.upper())}%)" if odds and i.upper() in odds else ""
        print(f"  {i:<6} {c:4d} ({100*c/n:.0f}%){o}")
    print(f"\nTop study sections:")
    for s,c in ss.most_common(8): print(f"  {c:4d} ({100*c/n:.0f}%)  {s}")
    print(f"\nWrote {p1}\n      {p2}")
    if not odds:
        print("Odds column omitted (set SUCCESS_RATE_CSV to the NIH Success-Rates-by-IC table to add it).")

if __name__=="__main__":
    main()
