# SSURGO Expansion

## Goal

Expand the SSURGO soil section in the Plinth report from 5 fields to 15+, organized into logical groups with subheadings. Add shrink-swell limiting factors via the SDM Tabular `cointerp` table. Update the info box with the full acronym, an explanation paragraph, and a hyperlink.

---

## Background

**SSURGO = Soil Survey Geographic Database** (USDA NRCS).

Currently the soil section shows only: Map Unit, Hydrologic Group, Drainage Class, Dominant Component, Taxonomic Class. This is the bare minimum. The `muaggatt` SDM Tabular table has 40 columns, many directly relevant to real estate development.

### New muaggatt fields to add (10 fields)

| Column | Description | Example value |
|---|---|---|
| `flodfreqdcd` | Flood frequency | None |
| `wtdepannmin` | Annual min. depth to water table (cm) | 30 |
| `brockdepmin` | Depth to bedrock (cm) | None |
| `niccdcd` | Non-irrigated land capability class (1–8) | 1 |
| `aws0100wta` | Available water storage 0–100cm (in.) | 16.28 |
| `engstafdcd` | Septic absorption field suitability | Very limited |
| `engdwobdcd` | Dwellings without basement suitability | Very limited |
| `engdwbdcd` | Dwellings with basement suitability | Very limited |
| `englrsdcd` | Local roads & streets suitability | Very limited |
| `forpehrtdcp` | Potential erosion hazard | Slight |

### Shrink-swell via cointerp

The `cointerp` SDM Tabular table stores component-level interpretation ratings with limiting factors. Structure:
- `seqnum=0`: overall rating ("Not limited" / "Somewhat limited" / "Very limited")
- `seqnum≥1`: limiting factors in order of severity (e.g., "Depth to saturated zone", "Shrink-swell")

Confirmed present for our test component (cokey 26777290):
- `ENG - Dwellings W/O Basements`: Very limited → limited by "Depth to saturated zone" + "Shrink-swell"
- `ENG - Septic Tank Absorption Fields`: Very limited → limited by "Depth to saturated zone"

**Approach**: Batch query all cokeys for all survey areas in one SDM Tabular call. Fetch seqnum 0–3 for 4 engineering rules. Store in a new `ssurgo_cointerp_engr` table. At query time, join to the dominant component to get rating + top limiters.

**Engineering rules to fetch:**
- `ENG - Dwellings W/O Basements`
- `ENG - Dwellings With Basements`
- `ENG - Septic Tank Absorption Fields`
- `ENG - Local Roads and Streets`

---

## Report Organization

The soil section will be restructured from a flat list into **3 subgroups**:

### Physical Conditions
- Map Unit
- Dominant Component
- Hydrologic Group
- Drainage Class
- Slope
- Flood Frequency
- Depth to Water Table
- Depth to Bedrock

### Farmland & Water
- Land Capability Class (1=best → 8=worst, non-irrigated)
- Available Water Storage (0–100cm)
- Erosion Hazard

### Engineering Suitability
- Septic Absorption Fields — rating + top limiters
- Dwellings Without Basement — rating + top limiters (includes shrink-swell if present)
- Dwellings With Basement — rating + top limiters
- Local Roads & Streets — rating

**Classification** (at bottom, italicized)
- Taxonomic Class

---

## Info Box Updates

**Info box structure** (in order):
1. **Explanation paragraph**: High-level description of what SSURGO is and what the data represents. First use of the acronym expands to "Soil Survey Geographic Database (SSURGO)"; all subsequent uses in the box use the acronym only.
2. **Disclaimer paragraph** (existing): No foundation suitability, bearing capacity, or construction assessment is made or implied. Consult a licensed geotechnical engineer...
3. **Source attribution** with hyperlink to [USDA Web Soil Survey](https://websoilsurvey.sc.egov.usda.gov/).

---

## Files Changed

| File | Change |
|---|---|
| `plinth/db/migrations/006_ssurgo_expansion.sql` | Add 10 columns to `ssurgo_muaggatt`; create `ssurgo_cointerp_engr` table |
| `plinth/ingest/ssurgo.py` | Add `_fetch_muaggatt_via_sdm()`, `_fetch_cointerp_via_sdm()`, `_load_cointerp()`, update `_load_mapunits_and_muaggatt()` |
| `plinth/query/soil.py` | Expand SELECT columns; add `ssurgo_cointerp_engr` join |
| `plinth/report/context.py` | Expand `_build_soil()` with new fields + cointerp data; add `_fmt_eng_rating()` helper |
| `plinth/report/templates/report.html` | Restructure soil section into 3 groups; update info box |
| `docs/plinth.dbml` | Add new columns + `ssurgo_cointerp_engr` table |

---

## Implementation Notes

### muaggatt fetch strategy
Rather than expanding the WFS GML columns (unreliable, varies by layer version), add a dedicated `_fetch_muaggatt_via_sdm()` SDM Tabular query that runs after the WFS load. The mukeys are already in `ssurgo_mapunits` at that point.

```sql
SELECT mukey, flodfreqdcd, wtdepannmin, brockdepmin, niccdcd, aws0100wta,
       engstafdcd, engdwobdcd, engdwbdcd, englrsdcd, forpehrtdcp
FROM muaggatt
WHERE mukey IN (...)
```

Batch in groups of 500 mukeys. Upsert into the new columns of `ssurgo_muaggatt`.

### cointerp fetch strategy
One batch SDM Tabular query per ingest using areasymbol join:

```sql
SELECT ci.cokey, ci.mrulename, ci.seqnum, ci.interphrc
FROM cointerp ci
JOIN component c ON ci.cokey = c.cokey
JOIN mapunit mu ON c.mukey = mu.mukey
JOIN legend l ON mu.lkey = l.lkey
WHERE l.areasymbol IN ('OK021', ...)
AND ci.mrulename IN (
    'ENG - Dwellings W/O Basements',
    'ENG - Dwellings With Basements',
    'ENG - Septic Tank Absorption Fields',
    'ENG - Local Roads and Streets'
)
AND ci.seqnum <= 3
```

### Displaying limiters in the report
For each engineering field, show: `Rating (limited by: Factor 1, Factor 2)` e.g.:
> Very limited *(limited by: depth to saturated zone, shrink-swell)*

Build a helper `_fmt_eng_rating(rating, limiters)` in `context.py`. If rating is "Not limited" or limiters list is empty, show rating only.
