-- Migration 006: SSURGO muaggatt expansion + cointerp engineering suitability table
--
-- Adds 10 new columns to ssurgo_muaggatt and creates ssurgo_cointerp_engr
-- for engineering suitability ratings with limiting factors.

-- Additional muaggatt aggregate fields
ALTER TABLE ssurgo_muaggatt ADD COLUMN IF NOT EXISTS flodfreqdcd  TEXT;
ALTER TABLE ssurgo_muaggatt ADD COLUMN IF NOT EXISTS wtdepannmin  INTEGER;
ALTER TABLE ssurgo_muaggatt ADD COLUMN IF NOT EXISTS brockdepmin  INTEGER;
ALTER TABLE ssurgo_muaggatt ADD COLUMN IF NOT EXISTS niccdcd      TEXT;
ALTER TABLE ssurgo_muaggatt ADD COLUMN IF NOT EXISTS aws0100wta   NUMERIC;
ALTER TABLE ssurgo_muaggatt ADD COLUMN IF NOT EXISTS engstafdcd   TEXT;
ALTER TABLE ssurgo_muaggatt ADD COLUMN IF NOT EXISTS engdwobdcd   TEXT;
ALTER TABLE ssurgo_muaggatt ADD COLUMN IF NOT EXISTS engdwbdcd    TEXT;
ALTER TABLE ssurgo_muaggatt ADD COLUMN IF NOT EXISTS englrsdcd    TEXT;
ALTER TABLE ssurgo_muaggatt ADD COLUMN IF NOT EXISTS forpehrtdcp  TEXT;

-- Component-level engineering interpretation ratings with limiting factors.
-- Each row is one (component, rule, seqnum) tuple:
--   seqnum=0 → overall rating ("Not limited" / "Somewhat limited" / "Very limited")
--   seqnum≥1 → limiting factors in order of severity (e.g. "Shrink-swell", "Wetness")
CREATE TABLE IF NOT EXISTS ssurgo_cointerp_engr (
    cokey      TEXT    NOT NULL,
    mukey      TEXT    NOT NULL,
    mrulename  TEXT    NOT NULL,
    seqnum     INTEGER NOT NULL,
    interphrc  TEXT,
    PRIMARY KEY (cokey, mrulename, seqnum)
);

CREATE INDEX IF NOT EXISTS ssurgo_cointerp_engr_mukey_idx
    ON ssurgo_cointerp_engr (mukey);
CREATE INDEX IF NOT EXISTS ssurgo_cointerp_engr_cokey_idx
    ON ssurgo_cointerp_engr (cokey);
