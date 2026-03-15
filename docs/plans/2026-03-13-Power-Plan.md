# Power & Electrical Infrastructure — Report Section Plan

**Date:** 2026-03-13  
**Status:** Draft / Planning  
**Depends on:** `2026-03-11-New-Data-Sources-Plan.md` (data already ingested)

---

## Overview

We have four power datasets ingested and ready:

| Dataset | Table | Rows |
|---|---|---|
| EIA-860 Power Plants | `eia_power_plants` | 16,132 |
| HIFLD Electric Service Territories | `electric_service_territories` | 2,931 |
| HIFLD Transmission Lines | `electric_transmission_lines` | 52,244 |
| HIFLD Substations | `electric_substations` | 10,923 |

These enable a meaningful **Electrical Infrastructure** subsection within the existing **Section 7 — Infrastructure & Access** (currently broadband-only). Power is a natural fit there rather than a new top-level section.

---

## What AEC Professionals and Commercial Developers Actually Need

Before listing data fields, it helps to frame the user questions:

- **"Who do I call to get power to this site?"** — Utility name, contact, entity type
- **"How expensive will it be to connect?"** — Distance to substation drives extension cost; voltage class signals available capacity
- **"Can this site support a large commercial/industrial load?"** — High-voltage transmission proximity is a proxy for grid headroom
- **"What does the grid look like around here?"** — Generation mix nearby; any renewables?
- **"Are there any constraints I should know about?"** — Dual-territory overlap, proximity to major infrastructure

---

## Proposed Content

### Subsection 7B: Electrical Infrastructure

Place immediately after the broadband subsection.

---

#### 1. Electric Utility Provider

**Source:** `electric_service_territories`

| Field | Description |
|---|---|
| Utility name | E.g., "Public Service Co. of Oklahoma" |
| Entity type | Investor-Owned / Cooperative / Municipal |
| EIA Utility ID | For reference/contact lookup |
| State | |

**Edge case:** If the site falls on or near a territory boundary, it may match two utilities. Surface both with a note ("Site may be in a boundary area — confirm service with both utilities before proceeding"). This is not uncommon (~5% of sites).

**Practical value:** First thing a developer needs before calling for a service application. Entity type matters — cooperatives often have different interconnection processes and timelines than IOUs.

---

#### 2. Nearest Substation

**Source:** `electric_substations`

Show the nearest 3 substations within 15 miles.

| Field | Description |
|---|---|
| Name | Station name (many are "UNKNOWN" in HIFLD — show if available) |
| Distance (mi) | Geodesic distance from site |
| Max voltage (kV) | Highest voltage level at the station |
| Min voltage (kV) | Distribution voltage level |
| Number of lines | Circuit count (proxy for capacity) |

**Practical value:** Substation distance is the single biggest variable in estimating electrical service extension cost. A site 0.5 miles from a 69kV substation vs. 5 miles from a 138kV substation tells very different stories for a large commercial user.

**Note on data quality:** HIFLD substation names are frequently "UNKNOWN." Show name only when it's a real name; otherwise just show distance and voltage. Don't show "UNKNOWN116547" — it's noise.

---

#### 3. Nearest Transmission Lines

**Source:** `electric_transmission_lines`

Show the nearest line in each voltage class within 10 miles. Group by voltage class rather than listing every individual line segment.

| Voltage Class | Nearest Distance | Owner |
|---|---|---|
| 345kV+ (Bulk transmission) | X.X mi | Utility name |
| 100–161kV (Sub-transmission) | X.X mi | Utility name |
| 69kV (Distribution feeder) | X.X mi | Utility name |
| <69kV | X.X mi | Utility name |

**Practical value:** Voltage class tells you what kind of load is feasible nearby. A 230kV+ line within 2 miles means the grid can support large industrial loads; only distribution voltage nearby suggests limited capacity without major infrastructure investment.

**Filter:** Only show voltage classes that actually have a line within 10 miles. Don't show empty rows.

---

#### 4. Nearby Generation (within 25 miles)

**Source:** `eia_power_plants` (operating plants only, `operating_status = 'OP'`)

Two displays:

**A. Nearest plants table** — Top 5 nearest operating plants:

| Plant Name | Fuel Type | Capacity (MW) | Distance |
|---|---|---|---|
| Northeastern | Natural Gas | 1,477 MW | 10.9 mi |
| Tulsa | Natural Gas | 348 MW | 16.4 mi |

**B. Generation capacity summary** — Total MW within 25 miles by fuel type (bar chart or simple kv-grid):

| Fuel | Total Capacity (MW) |
|---|---|
| Natural Gas | 4,161 |
| Wind | 820 |
| Solar | 45 |
| Coal | 0 |

**Fuel type display names** (map EIA codes to human-readable):
- `NG` → Natural Gas
- `SUN` → Solar
- `WND` → Wind
- `WAT` → Hydro
- `NUC` → Nuclear
- `COL` → Coal
- `LFG` → Landfill Gas
- `OIL` → Oil/Petroleum
- `GEO` → Geothermal
- `OTH` / `OG` / `BIT` / etc. → Other

**Practical value:** Generation mix nearby is relevant for sustainability reporting (LEED, BREEAM, ESG disclosures), energy procurement strategy, and understanding local grid reliability. A site surrounded only by aging coal or gas plants will have different energy cost and sustainability dynamics than one near major renewables.

---

### Map — Electrical Infrastructure

**This is the highest-value addition in this section.**

A Mapbox Static Image showing:

1. **Site marker** (standard pin)
2. **Service territory boundary** — Semi-transparent polygon outline (not filled — too visually heavy) in the utility's color or a neutral blue
3. **Transmission lines within 10 miles** — Colored by voltage class:
   - 345kV+: red/dark
   - 138–161kV: orange
   - 69–115kV: yellow
   - <69kV: light gray
4. **Substations within 15 miles** — Distinct marker (lightning bolt or square), sized by voltage
5. **Power plants within 25 miles** — Circle markers, colored by primary fuel type (green=wind/solar, blue=gas, gray=coal, etc.)

**Suggested map extents:** ~15-mile radius bounding box, so transmission infrastructure is clearly visible. Plants at 25 miles may fall off the map — that's fine, they still show in the table.

**Map size:** Same format as other Plinth maps (landscape, full section width).

---

## What We Are NOT Including (and Why)

| Item | Reason excluded |
|---|---|
| EIA utility financial data | Not available in our dataset; out of scope |
| Rate schedules / pricing | Too variable; not in EIA-860 |
| Planned/under-construction plants | EIA data includes these but they add noise for site selection |
| Individual line ownership details | Owner often = the same utility as the territory; redundant |
| Transmission line ampacity/capacity | Not in HIFLD data |
| Smart grid / reliability indices (SAIDI) | Not in our dataset |

---

## Data Quality Notes

- **HIFLD substation names:** ~40% are "UNKNOWN" or generic tap designations. Voltage and line count data is more reliable than names. Design the display to degrade gracefully.
- **Territory overlap:** Some sites (especially rural/peri-urban) fall in both an IOU territory and a co-op boundary. This is real and should be surfaced, not hidden.
- **EIA plant data vintage:** EIA-860 is annual; our data is from the most recent ingested year. Show the data year in the methodology section.
- **Transmission line ownership:** `owner` field is not always populated. Fall back to "operator unknown" gracefully.

---

## Implementation Plan

### Phase 1: Query Layer
- [ ] Create `plinth/query/electric_infrastructure.py`
  - `query_electric_infrastructure(lat, lon)` returning:
    - `service_territories` list (usually 1, sometimes 2)
    - `nearest_substations` list (top 3 within 15 mi, filtered to real names when available)
    - `transmission_lines` grouped by voltage class (nearest in each class within 10 mi)
    - `nearby_plants` list (top 5 nearest operating, within 25 mi) + `capacity_by_fuel` dict
- [ ] Register in `plinth/query/__init__.py`

### Phase 2: Context Builder
- [ ] Add `_build_electric_infrastructure(elec_q)` to `plinth/report/context.py`
- [ ] Add call to `build_report_context()`

### Phase 3: Map
- [ ] Add `_electric_infrastructure_map(lat, lon, elec_q)` to map utilities
- [ ] Layers: territory boundary, tx lines (by voltage), substations, plants

### Phase 4: Template
- [ ] Add Section 7B "Electrical Infrastructure" to `report.html` after broadband
- [ ] Utility provider kv-grid
- [ ] Substations table
- [ ] Transmission lines by voltage class kv-grid
- [ ] Nearby plants table + fuel summary
- [ ] Map
- [ ] Inline disclaimer (HIFLD data quality caveat, EIA data year)

### Phase 5: Data Sources section

Add/update entries in `_SOURCE_DISPLAY` in `plinth/report/context.py` with human-readable names. All four sources store data in PostGIS.

```python
"eia-860":                    ("EIA-860 Electric Power Plants & Generators",         "PostGIS", None),
"hifld-electric-territories": ("Electric Utility Service Territories (DHS HIFLD)",   "PostGIS", None),
"hifld-substations":          ("Electric Power Substations (DHS HIFLD)",              "PostGIS", None),
"hifld-transmission-lines":   ("Electric Transmission Lines (DHS HIFLD)",             "PostGIS", None),
```

> **Note:** These keys are already in `_SOURCE_DISPLAY` with shorter placeholder names from the initial implementation. This phase updates them to the names above.

---

## Resolved Design Decisions

### Map Bounding Box — Dynamic
Compute the bounding box from all visible features: nearest substation (≤15 mi), nearest transmission lines (≤10 mi), and nearest power plants (≤25 mi). Add 20% padding, cap at a 30-mile radius. This gives a tight, informative view when infrastructure is nearby and expands gracefully when the site is more remote — better than a fixed radius that either wastes space or clips relevant features.

### Fuel Type Color Palette
Define a consistent palette used for both map markers and any future charts:

| Fuel | Color | Hex |
|---|---|---|
| Natural Gas | Amber | `#F59E0B` |
| Wind | Green | `#10B981` |
| Solar | Gold | `#EAB308` |
| Coal | Dark Gray | `#6B7280` |
| Nuclear | Purple | `#8B5CF6` |
| Hydro | Blue | `#3B82F6` |
| Landfill Gas | Olive | `#84CC16` |
| Oil/Petroleum | Brown | `#92400E` |
| Other | Slate | `#94A3B8` |

### Substation Name Display
Show all substations with valid voltage data, regardless of name availability. When the HIFLD name is "UNKNOWN" or a generic tap ID (e.g., "TAP142959"), display "Unnamed substation" rather than the raw ID — the raw IDs are internal HIFLD identifiers with no public meaning. Voltage class and distance are the meaningful fields.

### Territory Boundary on Map
Light polygon fill (5% opacity) in a neutral blue + medium-weight outline. Gives enough visual context to read the territory boundary without burying the infrastructure layers underneath. When two territories overlap the site, show both outlines in distinct colors (blue and orange).

---

