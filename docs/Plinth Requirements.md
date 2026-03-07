# Plinth — Product Requirements

> **Status:** v0.3 — Updated post Round 2 peer review (Tech, Product, Marketing, Legal)
> **Scope:** Phased national coverage. Zoning / local regulatory intelligence is explicitly **out of scope** for these phases.
> **Note on placeholders:** Product name, pricing tiers, and pricing amounts are working placeholders only. None of these are final decisions.

---

## 1. Product Vision

**Plinth** is a paid, on-demand PDF report — generated from a simple web portal — that gives real estate developers, owner's representatives, architects, and design-build professionals a professionally formatted **site context and environmental risk snapshot** for any US address or GPS coordinate.

A user enters an address, pays a fee, and receives a downloadable PDF within minutes. The report aggregates 100+ site context variables — environmental risk, physical conditions, climate, solar, and demographic data — into a client-ready summary that addresses the physical and contextual questions asked in the first week of evaluating a site. It does **not** replace zoning analysis, entitlement review, or professional engineering — and does not claim to.

The PDF is the primary deliverable. A future phase will expose an interactive web experience from which the PDF is exported.

This is **not** a legal opinion, stamped engineering study, or substitute for any licensed professional. It is an early-stage site context tool for preliminary screening.

> **Positioning:** The comparison is not to free public tools. The comparison is to *calling your civil consultant and having a junior analyst pull FEMA, NOAA, Census, and IECC data into a PowerPoint over three days*. This report replaces that step — in minutes, in a format ready for an IC memo appendix, client pitch, or go/no-go checklist.

---

## 2. Target Users

| Segment | Description | Why They Buy |
|---|---|---|
| **Primary ICP (Year 1)** | Small infill multifamily / mixed-use developers — 2–15 person shops doing 3–10 deals/year, no in-house GIS staff | Own the site selection decision; highest screening volume; most willing to swipe a card to save 3–5 hours; need something credible enough for an equity partner or IC deck |
| **Secondary** | Owner's representatives, corporate real estate managers (healthcare, retail, industrial) at boutique firms | Screen sites on behalf of institutional owners; value standardization and a defensible paper trail |
| **Word-of-mouth channel** | Architects, GCs, and design-build firms who participate in early feasibility | Inherit sites; don't select them — but receive reports from clients and refer back |

> **Trigger moment:** The primary buyer purchases *after* receiving a broker OM or walking a site, and *before* committing to a Phase I ESA or civil engagement. The job to be done: "Does this site have any red flags I'd be embarrassed to miss in front of my equity partner or lender?"

> **Year 1 geographic focus:** 2–3 US metros with high infill development activity. Expand nationally as routing and data coverage grows.

---

## 3. Pricing Model *(placeholder — all figures and tiers are TBD)*

| Tier | Placeholder Price | Scope |
|---|---|---|
| Single report | ~$99 | All Phase 1 layers, one report |
| Project pack | ~$399 | ~5 reports — for one active deal's screening phase |
| Quarterly pack | ~$999 | ~15 reports — for shops with active pipelines |

> **Pricing notes (decisions deferred):**
> - Final price and tier structure require validation testing — these are order-of-magnitude placeholders only.
> - AEC firms buy tools on annual/project plans, not per-transaction card swipes. A firm-level annual plan is the right long-term growth model and should be evaluated in Phase 2.
> - Receipts must include a **"Project Name / Code"** field so firms can expense reports to a job code.
> - Credit packs with unused balance may be subject to state unclaimed property / escheatment laws. Expiration policy must be reviewed and approved by counsel before credit packs are offered for sale. This is a **launch-blocking requirement** — do not offer credits until counsel has reviewed DE, CA, and company state of incorporation requirements.
> - Credit packs also require a money transmitter / stored-value analysis (distinct from escheatment). Consult counsel on whether the credit pack structure triggers prepaid card or money transmission licensing in any state.

---

## 4. Phased Roadmap

### Phase 1 — National MVP

All data sourced from **free national datasets** (public domain or open APIs). No local or municipal data.
All spatial demographics computed using **straight-line radius buffers** (1 mi, 5 mi, 10 mi), clearly labeled.

**Geographic scope:** 50 US states + DC. Puerto Rico and US territories out of scope in Phase 1. Alaska and Hawaii included but may have reduced data coverage (FEMA NFHL is sparse in AK; climate stations are more distant) — addresses in reduced-coverage areas return inline data-availability flags, not silent failures.

### Phase 2 — National "Harder" Features

- Drive-time / isochrone demographics (self-hosted routing engine, state-by-state expansion)
- Interactive web portal; PDF becomes an export
- Firm-level annual subscription plans

### Future (Post-Phase 2, Not In Scope Here)

- Zoning-lite layer: jurisdiction ID, district label, link to municipal code, basic overlay flags
- Parcel boundary integration (commercial license, e.g., Regrid per-parcel API)
- Multi-site comparison and portfolio screening

### Out of Scope (All Phases)

- Zoning / land-use regulatory intelligence (heights, setbacks, FAR, permitted uses)
- Building code or ordinance lookups
- RAG / LLM on municipal documents
- Legal or compliance opinions of any kind
- Local crime data
- Property valuation or pro forma

---

## 5. Phase 1 — Detailed Report Requirements

### 5.1 Report Sections

#### Section 1 — Executive Summary *(1–2 pages)*

- Site address, coordinates, report date, report version ID
- **Risk Summary Table** — tabular data summary for flood zone, seismic PGA, wildfire percentile, soil group, air quality status. No color-coded risk ratings. See design principle #2 and legal note below.
- Population snapshot (5-mi straight-line radius)
- IECC Climate Zone designation (cite specific edition: DOE/PNNL IECC 2021 or current at build time)
- Key data flags in plain language (e.g., "Site is in FEMA Zone AE — see Section 2")
- **Prominent disclaimer block on cover page** (see §11.2)

> **Risk dashboard note:** A color-coded green/yellow/red flag system assigns risk severity — which is an editorial judgment and potentially an engineering determination. If color coding is used, the color thresholds and their sources (e.g., "red = FEMA Special Flood Hazard Area as defined by NFHL") must be explicitly stated and defensible as direct data lookups, not derived ratings. Consult counsel before implementing any color rating system. A tabular data summary is safer than a color dashboard and is the default.

> **Flag language guidance:** Flags must present data and direct to verification — not draw conclusions. Example: ~~"Flood insurance likely required"~~ → **"FEMA Flood Zone AE — properties in this zone are typically within the Special Flood Hazard Area. Verify current map status and insurance requirements with your lender and local floodplain manager."**

---

#### Section 2 — Environmental Risk

| Data Layer | Outputs |
|---|---|
| **Flood Risk** | FEMA flood zone classification (A, AE, VE, X, etc.), 100-yr / 500-yr floodplain status, Base Flood Elevation (BFE) where available, NFHL snapshot date. **Must explicitly distinguish between: (a) mapped low-risk zone, (b) mapped high-risk zone, and (c) area not yet mapped by FEMA — ~15–20% of the US has no FEMA flood mapping; these must never be silently reported as Zone X.** No insurance conclusions drawn. Direct user to FIRMette for current map status. |
| **Seismic Risk** | USGS Peak Ground Acceleration (PGA) value from national hazard maps, historical earthquake frequency within 50 mi (count + max magnitude, defined time window e.g., M3+, last 50 years), USGS seismic hazard percentile vs national. Note: *"Seismic Design Category (SDC) is an engineering determination per ASCE 7 and requires a licensed structural engineer."* |
| **Wildfire Risk** | USDA Forest Service Wildfire Hazard Potential (WHP) percentile, Wildland-Urban Interface (WUI) classification. Source, methodology, and data vintage explicitly cited in-field. |
| **Soil Profile** | USDA SSURGO dominant map unit: soil series name, USDA Hydrologic Soil Group (A/B/C/D), drainage class, shrink-swell potential class, USDA taxonomic classification. **Present as raw USDA taxonomy only — do not derive any suitability rating or foundation assessment.** Add note: *"Consult a licensed geotechnical engineer for foundation design."* |
| **Air Quality** | Nearest EPA AQS monitor: annual PM2.5 concentration (µg/m³) and ozone design value (ppb). Monitor name, distance from site, data year. Note: *"AQS data typically lags 6–18 months; not a real-time air quality index."* Flag if no monitor within 50 miles. |
| **FEMA National Risk Index** | FEMA's composite natural hazard risk score (tract-level), percentile vs. national average, component breakdown. **Attribution required:** this is FEMA's model output, not a derived rating. Label explicitly: *"Source: FEMA National Risk Index — FEMA's composite model. See fema.gov/nri for methodology."* |

---

#### Section 3 — Physical Context

| Data Layer | Outputs |
|---|---|
| **Elevation** | Site elevation (ft/m), elevation range within 1-mi radius, DEM-derived map image |
| **Slope** | Average slope %, max slope % within 500m radius. Descriptive band for reference: 0–5% / 5–15% / >15%. **Remove "significant grading likely" — that is a civil engineering determination.** Replace with: *"Slope >15% — consult a licensed civil engineer regarding grading and drainage requirements."* |
| **Terrain Map** | Hillshade or slope heatmap image, scale bar, north arrow, Mapbox attribution |
| **Land Cover** | Dominant NLCD land cover class within 500m (developed, forested, wetland, etc.), impervious surface % |
| **Hydrography** | Named water bodies within 1-mi radius, distance to nearest stream/river (NHDPlus HR — replaces USGS 3DHP which has incomplete national coverage in Phase 1) |

> **Slope calculation note (technical):** DEM clip must be buffered beyond the AOI before computing slope (use GDAL `DEMProcessing` with `-compute_edges`). Clipping exactly to the AOI produces incorrect edge values. Buffer at least 1 grid cell (~10m for 3DEP 1/3 arc-sec).

---

#### Section 4 — Climate & Weather

| Data Layer | Outputs |
|---|---|
| **Climate Normals** | 30-year monthly averages: high/low temp, precipitation, snowfall. NOAA station name and distance from site. Flag if nearest station > 15 miles. |
| **Degree Days** | Annual Heating Degree Days (HDD) and Cooling Degree Days (CDD) — with HVAC sizing context note |
| **Snowfall** | Average annual snowfall (inches), max monthly snowfall. Presented as observed climate data. Note: *"Structural snow load is an engineering determination per ASCE 7 and must be performed by a licensed structural engineer."* |
| **Humidity** | Average relative humidity by season |
| **Climate Zone** | IECC climate zone designation (e.g., "3A — Warm Humid") — cite specific edition: DOE/PNNL IECC 2021. Note: local adoption may vary. |
| **Freeze-Thaw** | Estimated annual freeze-thaw cycles (days crossing 32°F) |

> **Removed:** ASCE 7 wind speed design values (copyrighted; engineering determination). Structural snow load (same).
> **Climate sources:** NASA POWER API is primary (gridded, coordinate-level). NOAA/NCEI station normals used for station-level precision and as independent validation. Open-Meteo as fallback. See §7 for API rate-limit and caching requirements.

---

#### Section 5 — Solar

| Output | Description |
|---|---|
| Solar Path Diagram | Annual sunrise/sunset arc visualization (solstice + equinox), computed locally via Python `astral` library |
| Peak Sun Hours | Annual average peak sun hours per day (NASA POWER) |
| Seasonal Variation Table | Sunrise/sunset times by month (locally computed via `astral`) |
| Solar Data Note | Raw data only: latitude, peak sun hours, solar irradiance (kWh/m²/day). **Remove "qualitative assessment of passive solar / PV potential"** — that is an opinion on energy engineering suitability. Present data and add: *"Consult a licensed architect or solar energy professional for site-specific passive solar or PV design."* |

> **Removed:** "Lot Orientation Note" — a lat/lon point has no lot geometry. South-facing exposure requires parcel boundaries (deferred). "Solar viability note" with qualitative assessment — removed per legal review; constitutes a derived opinion that may trigger architectural or energy engineering licensing concerns.

---

#### Section 6 — Demographic & Market Context

*Straight-line radius buffers: 1 mi, 5 mi, 10 mi. All buffers computed as area-weighted intersections of Census block groups to avoid population overcount in rural areas with large tracts.*

| Metric | Source |
|---|---|
| Total population by radius | US Census ACS 5-yr |
| Population density | US Census ACS 5-yr |
| Median household income | US Census ACS 5-yr |
| Renter vs. owner-occupied % | US Census ACS 5-yr |
| Age distribution (summary) | US Census ACS 5-yr |
| Household size | US Census ACS 5-yr |
| Housing unit count | US Census ACS 5-yr |
| Population growth trend (note) | ACS 5-yr vintage comparison — labeled with years compared and noted as overlapping samples |

*All radius buffers labeled "straight-line radius." Physical barriers (water, mountains) not accounted for until Phase 2 drive-time isochrones. Area-weighted intersections require a defined projection strategy: use PostGIS `geography` type for geodesic accuracy, especially near coasts and borders.*

---

#### Section 7 — Infrastructure & Access

| Data Layer | Outputs |
|---|---|
| **Broadband** | FCC service availability, max advertised download/upload tier. **Inline disclaimer required:** *"FCC broadband data is self-reported by ISPs and may significantly overstate actual coverage. Treat as indicative. Verify directly with service providers before relying on broadband availability for site selection."* |
| **Road Access** | Distance to nearest arterial/highway (OSM-derived) |
| **Transit Proximity** | Distance to nearest transit stop (OSM-derived) |
| **Water/Sewer Note** | Flagged as "verify with local utility" — no authoritative national source for service area availability |

---

#### Section 8 — Data Sources & Methodology

- Full list of all data sources, versions, effective dates, and retrieval dates
- Distance to nearest climate station
- FEMA NFHL vintage and snapshot date
- Census ACS vintage (e.g., "2019–2023 ACS 5-Year Estimates")
- Disclaimer block (see §11 for required language and placement)
- Report generation timestamp and unique report version ID
- Report archive ID (see §11.8 re: retention)

---

### 5.2 Report Format

- Output: **PDF** (vector graphics, print-quality)
- Length: **8–12 pages** (executive summary front-loaded; dense methodology/sources in appendix)
- Design standard: Professional, institutional. White-space-forward. Must be shareable with clients and suitable for inclusion in feasibility study appendices. No consumer-facing aesthetics.
- Maps: Clean cartographic output with basemap, scale bar, north arrow, legend. **Mandatory: "© Mapbox © OpenStreetMap contributors" on every map image** per Mapbox ToS and ODbL.
- Charts: Consistent typography and color palette throughout
- Cover page: Site address, coordinates, report date, report ID, "Prepared for" field (entity name only pending FCRA analysis — see §11.6), product branding, **prominent disclaimer block**
- **Prototype the full PDF layout** (all 8 sections, all maps, realistic data) before beginning data pipeline work. WeasyPrint layout issues compound in long documents and are cheaper to find pre-pipeline.

#### PDF as a Growth Surface

Every report that gets forwarded (to lenders, equity partners, architects) is a potential referral. Design accordingly:
- Subtle persistent footer: *"[Product] — site-intelligence.com · Report ID: [XXXXX]"*
- Final appendix page: brief "About this report" with soft CTA and referral note for first-time users
- Cover page QR code linking to report re-order (or marketing site if product URL changes)
- Team Pack / white-label cover: allow firm name on cover; retain a *"Powered by [Product]"* attribution line that survives forwarding (even on white-label versions)

---

## 6. Phase 2 — Harder National Features

### 6.1 Drive-Time / Isochrone Demographics

Replace (or supplement) radius-based demographics with **drive-time catchment areas**:

- Isochrone polygons for 10, 20, 30, and 45-minute drive times
- Census demographic rollups within each isochrone using area-weighted block group intersections
- Fixes the "Vashon Island problem" — physical barriers naturally excluded from catchment area
- Isochrones cached by origin point (snapped to 100m grid) + time interval

**Self-hosted routing engine:**
- Preferred: **Valhalla** or **OpenRouteService (ORS)** (Docker, OSM-based)
- Data: OpenStreetMap `.osm.pbf` regional extracts (Geofabrik)
- Infrastructure note: Valhalla national tile build requires 30–60 GB RAM — build state-by-state

### 6.2 Web Portal — Interactive Experience

- Site map with layer toggles (flood zone, seismic, land cover)
- Adjustable radius / drive-time parameter
- Multi-site comparison (2–3 sites)
- PDF export from interactive view

PDF becomes an *export*, not the *product* — this is the transition from a document tool to a full site intelligence platform.

### 6.3 Additional Phase 2 Layers *(TBD priority)*

| Feature | Notes |
|---|---|
| Light Pollution | VIIRS nighttime lights (NASA Earthdata) |
| Walk Score | Walk Score API (paid) |
| Traffic Counts | AADT (FHWA HPMS or state DOT) |
| Economic Context | BLS employment, BEA GDP by MSA, FRED indicators |
| Solar Detail | NREL NSRDB (1k/day rate limit — Phase 2 only) |

---

## 7. Tech Stack

### 7.1 Core Infrastructure

| Component | Technology | Notes |
|---|---|---|
| **Database** | PostgreSQL 15+ with PostGIS | Vector spatial data; spatial indexes; buffer and point-in-polygon queries. Also hosts job queue. |
| **Raster Storage** | Cloud object storage (Backblaze B2 or AWS S3) | Individual tile COG files per dataset; **never** stored in Postgres. Maintain a PostGIS tile index table (`raster_tiles`: bounds geometry, s3_key, dataset, resolution). |
| **Raster Processing** | GDAL / rasterio (Python) | Clip bounding box around site; extract stats. Buffer beyond AOI before slope computation. |
| **Backend API** | Python (FastAPI) | Report requests, data assembly, job dispatch |
| **Job Queue** | PostgreSQL-based (`pgqueuer` or `SKIP LOCKED` pattern) | Redis eliminated — one fewer service. Requires: idempotency key per report, worker concurrency cap, job lease/timeout + reaper process for stuck jobs. |
| **PDF Generation** | **WeasyPrint + Jinja2** (single template system; do not introduce ReportLab) | HTML/CSS → PDF; maps and charts embedded as pre-rendered PNGs. Budget 2–5 sec render time per report. |
| **Map Rendering** | Mapbox Static Images API (MVP — free ≤100k/month) → self-hosted MapLibre Phase 2 | **Mapbox free tier is not a guaranteed budget line** — set a hard monthly cost ceiling and implement a fallback (MapLibre self-hosted static rendering) before hitting that ceiling. |
| **Geocoding** | Google Maps Geocoding API or Mapbox Geocoding API (day one) | **Never Nominatim** for a paid product. A bad geocode corrupts every data point. Cost: ~$5/1,000 requests. **ToS compliance required:** Google restricts caching geocode results with non-Google basemaps; verify permitted use case before mixing providers. |
| **Solar Calculations** | Python `astral` library (local computation) | Sunrise/sunset, solar path, solar noon — no external API needed. |
| **Routing (Phase 2)** | Valhalla or ORS (self-hosted Docker) | State-by-state expansion; CONUS needs 30–60 GB RAM. |
| **Containers** | Docker / Docker Compose | Local dev + staging |
| **Object Storage (local dev)** | MinIO | S3-compatible local emulation |
| **Frontend** | Next.js or plain HTML/JS + Stripe | Address input, payment confirmation, report download |
| **Payments** | Stripe | Per-report and credit-pack billing |
| **Monitoring** | Sentry + structured logging + hourly API health checks | Required before public launch. Must include: per-report error tracking (which sources failed), data staleness alerts, external API uptime checks, report quality flag if ≥2 sources fail. |

### 7.2 Data Integrity Infrastructure

**`data_source_registry` table** (required):

```
source_name | dataset_version | last_downloaded | update_frequency | next_review_date | notes
```

Every report pulls source metadata from this table to populate the Methodology section. Each data source must have a documented refresh runbook.

**`report_cache` table** with `geography` column and spatial index:
- Cache lookup before re-running a report
- **Do not use a flat 100m proximity check** — FEMA flood zone boundaries and census geography edges can shift materially within 100m. Use **dataset-specific cache keys**: FEMA polygon ID, Census tract/block group ID, POWER grid cell ID, etc., combined with a dataset version from `data_source_registry`.
- High-risk fields (flood zone, seismic PGA) must have **shorter or no cache TTL** — a FEMA LOMR issued between cache write and cache read could result in serving materially wrong data. Consult counsel on acceptable TTL for flood zone results specifically.

**`report_archive` table** (required, see §11.8):
```
report_id | generated_at | input_address | lat | lon | source_versions_json | pdf_storage_key
```

### 7.3 NASA POWER API — Rate Limiting & Caching Requirements

NASA POWER has no *published* strict rate limit but is a shared government resource. Do not treat it as unlimited:
- Implement **exponential backoff + retry** on all POWER requests
- **Pre-cache by grid cell**: POWER returns data at ~0.5° resolution (~50km). Cache results by POWER grid cell ID + parameter set + date range. Most reports within the same metro will hit the same cell.
- Never make synchronous POWER calls in the report generation hot path without a cache check first.
- Define failure behavior: if POWER is unavailable, what does the report show? (Inline "data unavailable — [date]" flag, not a silent blank.)

### 7.4 User-Facing Product Flows (Required Before Launch)

**Address verification before payment:**
- After address input, display a confirmation map (aerial basemap, geocoded pin) with prompt: *"Is this the correct location?"*
- User must confirm before proceeding to payment. This is the single highest-value UX step for reducing geocoding-error refunds and support tickets.

**Error state handling (all must be designed before launch):**
| Scenario | Behavior |
|---|---|
| Geocode failure (no match) | No charge; surface error with suggestion to try coordinate input |
| International address | No charge; message: "Service covers US addresses only" |
| Address in US territory / outside coverage | No charge; message with coverage scope |
| Federal land with no SSURGO data | Deliver report; show inline flag "SSURGO data unavailable for this location" |
| ≥2 data sources fail during generation | Deliver report with "Data Quality Flag" banner; auto-credit or discount (define threshold in spec) |
| All sources fail / timeout | No charge; retry queue with status notification |

**Report delivery & re-download:**
- Email notification with PDF download link on completion
- User portal: re-download any purchased report for minimum 90 days
- Do not make re-download dependent on email link survival

**Delivery SLA target (P95):** < 3 minutes from payment confirmation to PDF available. Define timeout threshold and queued-report behavior (notification + link when ready vs. synchronous wait).

---

## 8. Data Sources

### 8.1 Phase 1 Data Sources

| Section | Dataset | Provider | Access | Notes | URL |
|---|---|---|---|---|---|
| Geocoding | Google Maps or Mapbox Geocoding API | Google / Mapbox | API (paid, ~$5/1k) | **Day one. Never Nominatim.** Review ToS before mixing providers. | https://developers.google.com/maps/documentation/geocoding/overview |
| Elevation & Slope | USGS 3DEP (1/3 arc-sec, ~10m DEM) | USGS | Download + host (~3,500 tiles; PostGIS tile index + VRT) | Buffer clip for slope computation | https://www.usgs.gov/the-national-map-data-delivery |
| Flood Risk | FEMA NFHL (~3,200 county GDBs) | FEMA | Download + merge into unified PostGIS table | **Build derived unmapped-area layer.** Track snapshot date. Schema changes across county releases — document mapping. | https://www.fema.gov/national-flood-hazard-layer-nfhl |
| Natural Hazard Index | FEMA National Risk Index | FEMA | Download + host (tabular, census tract) | Present as FEMA's model output — explicit attribution required | https://resilience.climate.gov/datasets/FEMA::national-risk-index-census-tracts/about |
| Seismic Risk | USGS National Seismic Hazard Maps (PGA) | USGS | Download + host (raster/tabular) | Raw PGA only; no SDC derivation | https://www.usgs.gov/programs/earthquake-hazards/hazard-maps |
| Seismic History | USGS Earthquake Catalog API | USGS | API (free, 20k req/day) | Define explicit time window (50 yr) and magnitude threshold (M3+) in report text | https://earthquake.usgs.gov/fdsnws/event/1/ |
| Wildfire Risk | USDA Forest Service Wildfire Hazard Potential | USDA | Download + host (raster) | Cite source, version, methodology explicitly. Confirm this is the WHP product (not WFHP — names vary). | https://www.fs.usda.gov/rds/archive/Catalog/RDS-2015-0047-3 |
| Soil Profile | USDA SSURGO | USDA / NRCS | **Download state .gdb files** (not SDA API — 5–30s latency, frequent downtime) | Query `muaggatt` + `component` tables. Raw taxonomy only. | https://websoilsurvey.nrcs.usda.gov/ |
| Air Quality | EPA AQS API (annual summaries) | EPA | API (free) | Output: PM2.5 annual mean (µg/m³) and ozone design value (ppb) — **not** a real-time AQI index. AQS lags 6–18 months. Flag if no monitor within 50 miles. | https://aqs.epa.gov/aqsweb/documents/data_api.html |
| Climate (primary) | NASA POWER API | NASA | API (free, shared resource — implement backoff + grid-cell caching) | Temperature, precipitation, humidity, solar irradiance, degree days at any coordinate | https://power.larc.nasa.gov/ |
| Climate (station validation) | NOAA / NCEI Climate Normals (1991–2020) | NOAA | Download + host (tabular CSV) | Station name + distance. Flag sites > 15 miles from nearest station. | https://www.ncei.noaa.gov/products/climate-normals |
| Solar Calculations | Python `astral` library | Open source | Local computation | No external API call. | https://pypi.org/project/astral/ |
| Solar Irradiance | NASA POWER API | NASA | API (same call as climate) | Peak sun hours, irradiance (kWh/m²/day) — included in POWER request | https://power.larc.nasa.gov/ |
| Demographics | US Census ACS 5-Year Estimates | Census | API (free key) + download TIGER/Line block groups | Area-weighted intersections; PostGIS `geography` type for geodesic accuracy | https://www.census.gov/data/developers/data-sets/acs-5year.html |
| Census Geography | TIGER/Line Shapefiles (block groups, ~220k nationally) | Census | Download + host (vector) | | https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html |
| Broadband | FCC National Broadband Map | FCC | API (free key) | ISP self-reported; inline disclaimer required in report. Verify Location Fabric address matching method. | https://broadbandmap.fcc.gov/home |
| Hydrography | **NHDPlus HR** (replaces USGS 3DHP — better national coverage for Phase 1) | USGS | Download + host (vector) | 3DHP reserved for Phase 2 where coverage is available | https://www.usgs.gov/national-hydrography/nhdplus-high-resolution |
| Land Cover | National Land Cover Database (NLCD) | MRLC / USGS | Download + host (raster COG tile set, ~10–15 GB) | | https://www.mrlc.gov/ |
| Climate Zone | DOE/PNNL IECC 2021 Climate Zone Boundaries | DOE | Download + host (vector) | Cite specific edition; local code adoption may vary | https://www.energycodes.gov/development/buildings/climate_zones |
| Basemap | Mapbox Static Images API | Mapbox | API (free ≤100k/month; hard cost ceiling required + fallback plan) | **Attribution on every map image: "© Mapbox © OpenStreetMap contributors"** | https://docs.mapbox.com/api/maps/static-images/ |

### 8.2 Phase 2 Additional Sources

| Feature | Dataset | Provider | Access | URL |
|---|---|---|---|---|
| Drive-Time / Isochrones | OpenStreetMap road network | OSM | Download regional `.osm.pbf` (Geofabrik) | https://download.geofabrik.de/ |
| Routing Engine | Valhalla | Mapbox (open source) | Self-hosted Docker | https://github.com/valhalla/valhalla |
| Routing Engine (alt) | OpenRouteService | HeiGIT (open source) | Self-hosted Docker | https://github.com/GIScience/openrouteservice |
| Light Pollution | VIIRS Day/Night Band | NASA Earthdata | Download raster | https://earthdata.nasa.gov/learn/backgrounders/nighttime-lights |
| Walk Score | Walk Score API | Walk Score | API (paid) | https://www.walkscore.com/professional/api.php |
| Traffic Counts | FHWA HPMS | FHWA | Download | https://www.fhwa.dot.gov/policyinformation/hpms.cfm |
| Economic Data | BLS + FRED APIs | BLS / Fed Reserve | API (free key) | https://www.bls.gov/developers/ |
| Solar Detail | NREL NSRDB | NREL | API (free, 1k req/day limit) | Phase 2 only — rate limit too restrictive for Phase 1 at scale | https://developer.nrel.gov/docs/solar/nsrdb/ |

---

## 9. Key Design Principles

1. **Actionable over comprehensive.** Every data point must answer a real developer question. No data dumping.
2. **Present data; don't draw conclusions.** Present raw authoritative values (FEMA zone, USGS PGA, USDA soil taxonomy) and direct users to the appropriate licensed professional. Do not derive ratings, scores, or suitability judgments. This principle governs every section.
3. **Straight-line radius in Phase 1, clearly labeled.** All demographic buffers labeled "X-mile straight-line radius." Physical barriers not accounted for until Phase 2.
4. **FEMA unmapped ≠ safe.** Reports must explicitly distinguish "Zone X (mapped low risk)" from "area not yet mapped by FEMA." Never allow a site with no FEMA data to appear as low-risk by default.
5. **Raster data stays out of Postgres.** COG tiles in object storage; PostGIS tile index for lookup; bounding-box clips only.
6. **Cache correctly, not just aggressively.** Cache full reports, demographic rollups, isochrones, and solar calculations. Cache keys must be dataset-specific (FEMA polygon ID, Census tract ID, POWER grid cell). Flat proximity checks produce incorrect results near boundary edges. High-risk fields (flood, seismic) have shorter TTL or are excluded from caching.
7. **Visual quality is non-negotiable.** Report must be shareable with a client or lender without embarrassment. Prototype the PDF layout before building the data pipeline.
8. **Data freshness is tracked and displayed.** Every report shows effective dates for all data sources. `data_source_registry` tracks vintages and triggers review alerts. Never serve stale data silently.
9. **Start regional, expand by state.** Phase 2 routing builds state-by-state. Raster coverage expands as user geography grows.
10. **Disclaimers are prominent, not buried.** Appear: (a) pre-purchase, (b) cover page, (c) inline adjacent to flood, seismic, wildfire, soil, and broadband fields.
11. **The PDF is a growth surface.** Every report that gets forwarded is a potential referral. Footer, report ID, and CTA must survive forwarding.

---

## 10. Data Integrity & Freshness

| Data Source | Update Frequency | Action Required |
|---|---|---|
| FEMA NFHL | Continuous (LOMAs, LOMRs issued regularly) | Monthly: compare FEMA NFHL last-modified date against local snapshot; refresh if delta detected. Report must show snapshot date. High cache TTL risk — see §7.2. |
| Census ACS | Annual (2-year lag) | Update annually on new 5-year release. Track vintage year explicitly. |
| USGS 3DEP | Irregular | Annual review; 10m resolution is stable. |
| NLCD | Every 2–5 years | Annual check for new release. |
| USDA SSURGO | Annual updates by county | Annual refresh; maintain download date per state file. |
| USGS Seismic Hazard Maps | Irregular (~5 yr major cycles) | Annual review. |
| USDA Wildfire Hazard Potential | Annual | Refresh at dataset release. |
| NASA POWER | Continuous (rolling) | Grid cell cache TTL: 30 days max. |
| NOAA Climate Normals | Decadal (1991–2020 current) | Update when new normals period published. |
| OSM (Phase 2) | Continuous | Monthly regional `.osm.pbf` refresh; rebuild routing tiles on refresh. |
| IECC Climate Zone Boundaries | Per code cycle | Update when new edition published and adopted. |

---

## 11. Legal & Compliance Requirements

> These are requirements, not legal advice. Consult qualified counsel before public launch on every item marked **[LAUNCH-BLOCKING]**.

### 11.1 Terms of Service **[LAUNCH-BLOCKING]**

A ToS must exist before any public access and must include:
- Cap on damages (limit to report price paid)
- Warranty disclaimer (no representations on accuracy, completeness, or fitness for purpose)
- Explicit **third-party data disclaimer**: data provided by FEMA, USGS, EPA, Census, et al. is reproduced as-is; no warranty is made regarding the accuracy of third-party source data
- Governing law and venue selection
- Prohibition on using the report as a professional deliverable without independent professional review — **define this term clearly in ToS** (courts will need a specific definition; "5-minute glance by a PE" is not independently verifiable)
- Acknowledgment that users will verify all data with the authority having jurisdiction before relying on it
- **Redistribution restriction:** report is licensed to the purchaser; not for resale or transfer to third parties who have not agreed to these terms. Forwarding to a client or lender should be explicitly addressed — likely permitted with attribution, but consult counsel on third-party reliance exposure.
- Credit expiration policy (if credits offered)
- Refund policy with defined triggers (see §7.4)
- Dispute resolution / arbitration clause (if used, reference in disclaimer language)

### 11.2 Disclaimer Language **[LAUNCH-BLOCKING]**

Strengthen from aspirational to condition of use:

> *"This report does not constitute and shall not be relied upon as engineering, legal, architectural, or planning advice. All data is presented for preliminary screening purposes only and may be incomplete, outdated, or inaccurate. All findings must be independently verified with the applicable authority having jurisdiction, licensed professional, or data provider before use in any professional, financial, or design decision. [Company] makes no representations regarding the accuracy, completeness, or fitness for purpose of the information contained herein. Use of this report is subject to [Company]'s Terms of Service."*

**Placement:** (a) pre-purchase on checkout page, (b) cover page of every report, (c) inline adjacent to flood zone, seismic, wildfire, soil, and broadband fields.

### 11.3 Field-Specific Language Risks

| Field | Risk | Mitigation |
|---|---|---|
| Flood zone | Stale NFHL data may misclassify a remapped parcel | Show NFHL snapshot date; link to FIRMette; never state insurance conclusions |
| Soil profile | Derived suitability language may constitute geotechnical engineering practice | Raw USDA taxonomy only; geotechnical engineer referral note |
| Seismic output | SDC is an engineering determination | PGA only; licensed structural engineer note for SDC |
| Wildfire | Inaccurate assessment has been a litigation trigger in CA | Cite source; note data year; no superlatives |
| Slope | "Significant grading likely" is a civil engineering opinion | Remove "likely" — present raw % with civil engineer referral at >15% |
| Solar | "Solar viability assessment" may constitute architectural or energy engineering opinion | Remove qualitative assessment; present raw data only |
| Risk dashboard | Color-coded risk ratings are editorial judgments | Default to tabular data; if color coding used, each threshold must be sourced directly to a published standard and reviewed by counsel |
| FEMA NRI | Composite score could be mistaken for the product's own rating | Explicit attribution: "Source: FEMA NRI — FEMA's model" |
| Broadband | FCC data overstates coverage; high-stakes users (healthcare, data centers) may rely on it | Inline disclaimer required (see §7) |
| Snow/wind | ASCE 7 is copyrighted; design values require engineering application | Removed; present observed climate data only |

### 11.4 Professional Licensing **[LAUNCH-BLOCKING]**

Obtain a written opinion from counsel before public launch on whether the report's outputs constitute the practice of engineering, architecture, or planning in the initial launch states.

**What this means:** The relevant licenses are PE (civil, structural, geotechnical sub-disciplines), Licensed Architect, and in some states Professional Geologist. Each state's licensing board broadly defines "practice" — applying engineering principles to matters affecting public safety is often enough. The question is whether a data aggregation product that labels and contextualizes data (even without a stamp) crosses that line.

**What features trigger the inquiry:** Risk dashboard color coding, slope band labels, solar viability language (removed), any suitability or design-parameter language.

**Scope of opinion:** Initial opinion should cover the 6 highest-volume / most-aggressive-licensing states: CA, TX, FL, NY, WA, OR. Counsel should also address whether a federal *interstate commerce* argument (dormant Commerce Clause) or *federal preemption* argument provides any defense if a state board challenges a nationally-sold web product. These are not reliable shields — they are questions worth posing to counsel rather than assumptions to design around.

### 11.5 Map Attribution **[LAUNCH-BLOCKING]**

Every map image in every report must display: **"© Mapbox © OpenStreetMap contributors"** per Mapbox ToS and ODbL. Confirm attribution compliance in writing with Mapbox before launch. Non-compliance is a ToS breach.

### 11.6 Privacy & PII **[LAUNCH-BLOCKING]**

- **"Prepared For" field:** Limit to entity (company) names only until FCRA analysis is complete. Individual person name + address linkage may trigger FCRA applicability — do not launch with individual names in this field without counsel sign-off.
- **Privacy policy required** if any California users are served (CCPA). Address privacy policy to address logging, retention, and deletion rights.
- **Data security:** Encryption at rest and in transit for all address + report data. Define breach notification procedure and document security posture in privacy policy. CCPA imposes a reasonable security obligation alongside the notice obligation.
- **Address logging retention:** Define and disclose in privacy policy.

### 11.7 Insurance **[LAUNCH-BLOCKING]**

Obtain Technology E&O / Professional Liability coverage before public launch.
- **Minimum coverage:** $1M per occurrence / $2M aggregate (industry standard for SaaS data products — confirm with broker)
- **Scope confirmation required in writing:** Policy must explicitly cover "data products" and "technology products liability." Some Technology E&O policies exclude "professional services" — verify that delivery of site risk data to licensed professionals is covered. A separate professional liability rider may be required.

### 11.8 Report Archival & Audit Trail **[LAUNCH-BLOCKING]**

Every generated report must be archived with a unique report ID, retained for a minimum of **3–5 years** (confirm with counsel based on governing law state statute of limitations):
- Input parameters: address, lat/lon, report type
- Source versions used: snapshot of `data_source_registry` at generation time
- PDF stored in object storage with report ID key

This enables reproduction of exactly what was delivered if a user claims reliance on a specific report.

### 11.9 Remaining Open Items (Pre-Launch Checklist)

| Item | Status | Notes |
|---|---|---|
| ToS drafted and reviewed by counsel | ☐ | Include all §11.1 elements |
| Disclaimer language approved | ☐ | Placement in 3 locations |
| Professional licensing opinion (6 states) | ☐ | Including interstate commerce question |
| E&O policy bound (coverage confirmed in writing) | ☐ | $1M/$2M, tech products liability |
| CCPA privacy policy published | ☐ | |
| FCRA analysis complete | ☐ | Gate "Prepared For" individual names on this |
| Mapbox attribution confirmed in writing | ☐ | |
| Credit/pack escheatment policy approved | ☐ | DE, CA, incorporation state |
| Money transmitter analysis (credit packs) | ☐ | |
| Report archival system operational | ☐ | |
| Data breach / security policy in place | ☐ | |
| Sample report published on marketing site | ☐ | See §12 |
| State flood disclosure warnings (TX, FL, NC, SC) | ☐ | Consult counsel on statutory requirements |

---

## 12. Go-To-Market Considerations *(early-stage notes — not a marketing plan)*

> These are directional notes to inform product and feature decisions, not a GTM plan.

**ICP for Year 1:** Small infill multifamily / mixed-use developers in 2–3 US metros. 2–15 person shops. No in-house GIS staff. 3–10 deals per year. The principal or acquisitions lead is the buyer.

**The purchase trigger:** After a broker sends an OM or the principal walks a site. Before spending money on a Phase I ESA or civil engineering engagement. The job to be done: "Is there anything here that would embarrass me in front of my equity partner or kill the deal?"

**Against free alternatives:** Everything in this report is technically available for free. The pitch is not data — it's time and format: *"3–5 hours of intern time pulling FEMA, NOAA, Census, and IECC data into a PowerPoint, vs. a client-ready PDF in minutes."* The comparison should be to billable consultant time, not to free public tools.

**The PDF must attach to an existing deliverable.** The report should feel like a natural appendix to an IC memo, go/no-go checklist, or client pitch deck. If it doesn't integrate into something buyers already produce, it stays optional.

**Trust signals that matter in this market:**
- Institutional-looking design (not a startup product)
- Explicit data source citations with agency logos (FEMA, USGS, Census, NOAA)
- Clear methodology page with limitations
- AEC-standard disclaimer language ("screening-level," "not a substitute for licensed professional engineering")
- Advisor credibility: one civil engineer, one developer, one architect listed by name on the site
- Sample report available for download before purchase — this is table stakes

**Sample report requirement:** A downloadable sample report (real data, anonymized address) must be available on the marketing site before launch. This is the single highest-conversion asset for a $99+ data product. Users will not buy without seeing the output.

**Pricing and packaging notes (placeholder — see §3):**
- Receipts must include "Project Name / Code" field for expense coding
- Consider PO-friendly invoicing for owner's rep and corporate RE segments (Phase 2 pricing model)

**Product name:** "Plinth" — a plinth is the foundational base of a column; the layer established before anything is built. The name signals professional-grade AEC context without being literal or marketingy. It also scope-sets expectations correctly: this is the foundational data layer before a development decision, not a full site intelligence or zoning platform.

---

## 13. Out-of-Scope Features (Explicitly Deferred)

| Feature | Reason Deferred |
|---|---|
| Zoning code intelligence (heights, FAR, setbacks, uses) | City-by-city manual normalization; separate product phase |
| RAG / LLM on municipal documents | Depends on zoning feature |
| Parcel boundary data | Commercial licensing (Regrid ~$0.15/parcel or ~$50k/yr bulk); defer to funded phase |
| Building permit history | No clean national source |
| Property valuation / comps | Requires commercial feed (ATTOM, Zillow, etc.) |
| School district data | Not a developer go/no-go factor |
| Crime data | No national API; city-by-city |
| Pro forma / financial modeling | Out of scope |
| Multi-site comparison | Phase 2+ interactive web portal |
| Firm-level annual subscription | Phase 2+ pricing model |

---

## 14. Competitive Landscape

> This section is a working reference, not a full market analysis. All pricing is approximate / publicly available as of early 2026 and subject to change.

### Overview

The competitive space splits into three distinct tiers. No single competitor currently occupies the same position: a **per-report, on-demand, PDF-format, environmental + physical + demographic site snapshot at sub-$200 price points targeting small developers and owner's reps**. The closest analog in format is ClimateCheck (climate risk only, narrower scope). The larger platforms are structurally out of reach for the target buyer — either too expensive, too complex, or requiring GIS expertise the buyer doesn't have.

The most significant market event: **LightBox acquired UrbanFootprint in June 2025**, consolidating the two most capable enterprise platforms into a single company. This increases the enterprise depth at the top of the market but does nothing to address the small-developer segment.

---

### Tier 1 — Closest Competitors (Format or Content Overlap)

These are the tools most likely to come up in a head-to-head comparison with a potential buyer.

---

#### ClimateCheck
**URL:** https://climatecheck.com

| | |
|---|---|
| **What it does** | Per-property climate risk report covering flood, fire, heat, drought, and storm risk. Outputs a 1–100 "resiliency score" per risk category. Free basic tier for consumers; paid detailed reports (~$135/report via resellers like ERIS). API and enterprise portfolio tiers available. |
| **Target market** | Homebuyers, real estate agents, lenders, and property investors. Consumer-facing design. Enterprise API for mortgage and insurance workflows. |
| **Pricing** | Free (basic, consumer); ~$135/report (via resellers); enterprise API custom pricing |
| **Competitive strengths** | Closest format analog — on-demand report per address, accessible pricing, publicly readable output. Climate risk depth and multi-decade projections (up to 30 yr). Established brand in real estate portals. |
| **Competitive weaknesses** | **Climate risk only** — no physical context (elevation, slope, land cover), no demographics, no solar, no infrastructure, no soil, no climate normals, no IECC zone. Consumer-focused design and framing; not positioned as a professional AEC tool. Output is not a "client-ready appendix" — more of a risk score card. |
| **Our differentiation** | Broader scope (environmental + physical + climate + demographic + solar + infrastructure in one document); explicitly AEC-professional framing and format; raw data with source citations vs. a proprietary score. |

---

#### First Street
**URL:** https://firststreet.org · API docs: https://docs.firststreet.org/api

| | |
|---|---|
| **What it does** | Property-level climate and flood risk data API. Covers flood, fire, wind, heat, drought — with 30-year projections and scenario modeling. Formerly "Risk Factor" (rebranded 2024). Peer-reviewed, physically-based models. Bulk data downloads available. |
| **Target market** | Financial institutions, insurers, mortgage servicers, government agencies, property portals (Redfin, Realtor.com embed their data). Enterprise-first. |
| **Pricing** | Enterprise API — custom; contact sales. Not a consumer or per-report product for individual developers. |
| **Competitive strengths** | Best-in-class flood and fire risk modeling (peer-reviewed, not FEMA-derived). Forward projections to 2050. Embedded in major real estate portals — high brand recognition among buyers who have seen it in listings. |
| **Competitive weaknesses** | **No physical context, no demographics, no solar, no infrastructure.** Enterprise-only pricing and API integration — not accessible to a 5-person developer shop without a technical team. No PDF report output for practitioners. |
| **Our differentiation** | Format (PDF report, no integration required), accessibility (no API key or engineer needed), and breadth (flood is one of 8+ sections). We could theoretically *use* First Street data as a source in a future phase — their API is a potential data layer, not just a competitor. |

---

### Tier 2 — Broader Platform Competitors

These are real tools that AEC buyers may already use, but they are structurally misaligned with the target buyer in price, complexity, or use case.

---

#### LightBox (w/ UrbanFootprint — acquired June 2025)
**URL:** https://www.lightboxre.com · UrbanFootprint: https://urbanfootprint.com

| | |
|---|---|
| **What it does** | Comprehensive CRE data and analytics platform: parcel data, zoning, ownership, environmental hazards, transaction history, GIS layers, demographics. The June 2025 acquisition of UrbanFootprint added geospatial scenario modeling, climate risk layers, infrastructure analytics, and social equity indicators. |
| **Target market** | Enterprise CRE: national brokerages, institutional investors, lenders, developers with in-house analysts, government agencies. |
| **Pricing** | Custom enterprise pricing; not publicly disclosed. Described by users as "expensive." Annual contract, multiple users. |
| **Competitive strengths** | Broadest data coverage in the market (parcel + zoning + environmental + transaction + climate). Real-time data updates. Post-acquisition, deep geospatial analytics for portfolio-level analysis. GIS-native platform for power users. |
| **Competitive weaknesses** | **Requires a GIS analyst or dedicated CRE analyst to operate.** Enterprise pricing eliminates small developers and boutique owner's rep firms. Complexity and onboarding burden are antithetical to the "5-minute site check" use case. No on-demand per-report pricing. |
| **Our differentiation** | Price point (per-report vs. annual enterprise contract), simplicity (address in, PDF out, no GIS knowledge), and the specific small-developer ICP that LightBox actively does not serve. LightBox's UrbanFootprint acquisition actually validates the market — it signals that data aggregation + environmental + demographic context at the site level has commercial value. |
| **Consolidation note** | LightBox + UrbanFootprint creates a more formidable enterprise competitor but also leaves the small-developer segment even more underserved. A large competitor acquiring the only "accessible" enterprise option is a positive signal for this product's market position. |

---

#### ESRI ArcGIS Business Analyst
**URL:** https://www.esri.com/en-us/arcgis/products/arcgis-business-analyst

| | |
|---|---|
| **What it does** | The industry-standard demographic analysis and site selection platform. Drive-time trade area analysis, demographic profiling, competitor mapping, void analysis, suitability modeling. Runs on ArcGIS Online (cloud) or ArcGIS Pro (desktop). |
| **Target market** | Large retailers, franchise systems, government, healthcare systems, universities, corporate real estate departments. Requires GIS expertise. |
| **Pricing** | ~$1,100/user/year for ArcGIS Business Analyst Web App bundle (includes 6,000 service credits); enterprise pricing scales up significantly. |
| **Competitive strengths** | Industry standard — the tool that "real" GIS analysts use. Unmatched depth of demographic and consumer spending data. Trusted brand in AEC/government. |
| **Competitive weaknesses** | **GIS expertise required.** $1,100+/user/year is above the threshold for a 2-person developer shop to justify. Credit-based pricing (operations consume credits) makes cost unpredictable. No PDF report output for practitioners — output is maps/tables for analysts. Purely demographics — no environmental risk, no solar, no physical context. |
| **Our differentiation** | Format, price, accessibility, and scope. This is a tool for GIS analysts. Our product is for developers who don't have one. |

---

#### SiteSeer
**URL:** https://www.siteseer.com

| | |
|---|---|
| **What it does** | Site selection and market intelligence platform focused on **retail, restaurant, and franchise** expansion. Trade area analysis, sales forecasting, void analysis, cannibalization modeling, foot traffic. White space tool for identifying market gaps. |
| **Target market** | Retail chains, restaurant franchises, franchise development teams, retail brokers. Minimal residential or infill developer use. |
| **Pricing** | Custom — contact sales. Annual SaaS platform license. Not a per-report product. |
| **Competitive strengths** | Purpose-built for retail site selection workflows. ATOM™ module for franchise territory mapping. Integrates foot traffic and consumer behavior data. Intuitive for retail practitioners. |
| **Competitive weaknesses** | **Retail/restaurant-specific** — minimal relevance to multifamily, industrial, or mixed-use developers. No environmental risk layers. No engineering or physical context. Annual contract model. |
| **Our differentiation** | Entirely different use case. Retail developers may use both. No direct competition for small residential/mixed-use infill developers. |

---

### Tier 3 — Enterprise Climate Risk (Out of Price Range for Target Buyer)

These companies occupy the same *content space* (environmental/climate risk) but target large financial institutions, insurers, and government — not individual developers.

| Company | What it does | URL |
|---|---|---|
| **Jupiter Intelligence** | Forward-looking physical climate risk analytics for asset portfolios (15–50 yr projections). Stress testing for banks, insurers, infrastructure owners. | https://www.jupiterintel.com |
| **Moody's RMS** | Insurance-grade catastrophe risk modeling: flood, wind, wildfire, earthquake. Used by reinsurers and large property insurers. | https://www.rms.com |
| **CoreLogic Climate Risk** | Property risk analytics for mortgage lenders and servicers: flood, wind, wildfire, subsidence. Embedded in mortgage origination workflows. | https://www.corelogic.com |

> **Note:** These are potential *data source* partners or acquisition context, not direct competitors for the target buyer. If the product ever targets lenders or institutional owners, these become relevant as competitors.

---

### Tier 4 — Free / DIY Tools (The "Intern Problem")

These are the tools a resourceful intern or junior analyst uses when the developer *doesn't* buy this product. Understanding them is essential for the value pitch.

| Tool | What it does | Why buyers don't stop here | URL |
|---|---|---|---|
| **FEMA Flood Map Service Center / FIRMette** | Official FEMA flood zone lookup; downloadable FIRMette PDFs | Single data layer; raw PDF maps, not a professional presentation; no context for unmapped areas | https://msc.fema.gov |
| **USGS National Map Viewer** | Elevation, hydrography, land cover, and more in an interactive viewer | Interactive only; no exportable report; requires manual interpretation; no demographic or climate integration | https://apps.nationalmap.gov/viewer/ |
| **EPA AirNow / EnviroMapper** | Real-time and historical air quality | AQI only; no site context; no report format | https://www.airnow.gov |
| **Census Reporter / Social Explorer** | Demographic data visualization from ACS | Demographics only; no environmental risk; no export format suitable for a client; requires knowing which variables to pull | https://censusreporter.org · https://www.socialexplorer.com |
| **PolicyMap** | Multi-dataset demographic, economic, and housing data mapping | Primarily for nonprofits/government; no report export; no environmental risk; requires dataset knowledge | https://www.policymap.com |
| **NOAA Climate Data Online** | Station-based historical climate records | Raw data tables; not a site report; requires station selection expertise; no integration with other context | https://www.ncdc.noaa.gov/cdo-web/ |

> **Value pitch implication:** The "intern approach" requires pulling from 6–10 separate tools, knowing which variables matter, synthesizing into a coherent PowerPoint, and doing it for every site. For a developer screening 5 sites a month, that's a material cost in time and junior staff. This product replaces that workflow in minutes and produces a format that doesn't embarrass the developer in front of a lender or equity partner.

---

### Competitive White Space Summary

| Dimension | Enterprise Platforms | Climate-Only Reports | This Product |
|---|---|---|---|
| **Format** | Interactive platform / maps | Per-report PDF | Per-report PDF |
| **Environmental risk** | ✅ Deep | ✅ Climate only | ✅ Multi-hazard |
| **Physical context** | ✅ (LightBox) | ❌ | ✅ |
| **Demographics** | ✅ Deep | ❌ | ✅ |
| **Solar** | ❌ | ❌ | ✅ |
| **AEC-professional framing** | Partial | ❌ Consumer | ✅ |
| **Price point** | $1,100–$50k+/yr | Free–$135/report | ~$99/report (TBD) |
| **Requires GIS expertise** | Yes | No | No |
| **Target buyer: small developer** | ❌ Underserved | Partial | ✅ Primary ICP |
| **On-demand, no contract** | ❌ | ✅ | ✅ |

**The gap:** No current product delivers multi-hazard environmental risk + physical context + demographics + solar + infrastructure in a single, on-demand, client-ready PDF at a per-report price accessible to a small developer. That is the white space.
