#!/usr/bin/env python3
"""Weekly COVID-19 and flu levels for San Francisco and California.

Reads data/rv-dashboard.csv (CDPH) and data/wastewater-ca.csv (CDC NWSS) from the
current directory and prints one JSON object.

Each level synthesizes three indicators on the 5-step CDPH/CDC scale
(Very Low=1 .. Very High=5):
  - test positivity level   (CDPH, All Ages)
  - hospital admissions level (CDPH, All Ages)
  - wastewater level          (CDC WVAL: median site value, CDC thresholds)
Summary = mean of the available indicators, rounded half up.

Geography: CDPH reports by region, so San Francisco uses the Bay Area region for
test positivity and admissions, and San Francisco's own sewersheds for wastewater.
California uses the statewide CDPH row and the median of all California sites.
"""
import csv
import datetime as dt
import json
import statistics

LEVELS = ["Very Low", "Low", "Moderate", "High", "Very High"]
# CDC WVAL category upper bounds (https://www.cdc.gov/wastewater/about/wval.html)
WVAL_BOUNDS = {"SARS-CoV-2": [2.6, 4.9, 7.9, 11.6], "Influenza A virus": [2.4, 5.5, 10.2, 15.6]}
DISEASES = {"covid": ("COV", "SARS-CoV-2"), "flu": ("FLU", "Influenza A virus")}
GEOS = {"sf": ("Bay Area", "San Francisco"), "ca": ("California", None)}
STALE_DAYS = 9


def wval_level(value, pathogen):
    for i, bound in enumerate(WVAL_BOUNDS[pathogen]):
        if value < bound:
            return i + 1
    return 5


def main():
    today = dt.date.today()
    notes = []

    # CDPH test positivity and admissions (All Ages rows only)
    with open("rv-dashboard.csv", encoding="utf-8-sig") as f:
        cdph = [r for r in csv.DictReader(f) if r["AGE_GRP"] == "All Ages"]
    for r in cdph:
        r["_date"] = dt.datetime.strptime(r["WEEKENDING"], "%m/%d/%Y").date()
    cdph_week = max(r["_date"] for r in cdph)
    latest = {r["RPHO_REGION"]: r for r in cdph if r["_date"] == cdph_week}
    if (today - cdph_week).days > STALE_DAYS:
        notes.append(f"CDPH data is {(today - cdph_week).days} days old (week ending {cdph_week}).")

    # CDC wastewater, site level
    with open("wastewater-ca.csv", encoding="utf-8-sig") as f:
        ww = []
        for r in csv.DictReader(f):
            try:
                r["_val"] = float(r["site_wval"])
            except ValueError:
                continue
            r["_date"] = dt.date.fromisoformat(r["week_end"][:10])
            ww.append(r)

    out = {"week_ending": cdph_week.isoformat(), "levels": {}, "components": {}, "notes": notes}
    for geo, (region, county) in GEOS.items():
        out["levels"][geo], out["components"][geo] = {}, {}
        row = latest.get(region)
        for disease, (prefix, pathogen) in DISEASES.items():
            comp = {}
            if row:
                for key, col in (("test_positivity", f"{prefix}_TP_LEVEL"), ("admissions", f"{prefix}_ADM_LEVEL")):
                    if row.get(col) in LEVELS:
                        comp[key] = row[col]
            sites = [r for r in ww if r["pathogen_target"] == pathogen
                     and (county is None or county in r["counties_served"])]
            if sites:
                week = max(r["_date"] for r in sites)
                vals = [r["_val"] for r in sites if r["_date"] == week]
                comp["wastewater"] = LEVELS[wval_level(statistics.median(vals), pathogen) - 1]
                if (today - week).days > STALE_DAYS:
                    notes.append(f"{geo.upper()} {disease} wastewater data is from week ending {week}.")
            missing = {"test_positivity", "admissions", "wastewater"} - comp.keys()
            if missing:
                notes.append(f"{geo.upper()} {disease} level excludes: {', '.join(sorted(missing))}.")
            if comp:
                mean = statistics.mean(LEVELS.index(v) + 1 for v in comp.values())
                out["levels"][geo][disease] = LEVELS[int(mean + 0.5) - 1]
            else:
                out["levels"][geo][disease] = None
            out["components"][geo][disease] = comp
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
