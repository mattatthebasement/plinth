-- Migration 008: Drop unused fcc_broadband_availability table
--
-- This table was added in migration 007 as the planned target for a new FCC
-- bulk ingestor. The existing FccBroadbandIngestor (fcc_broadband.py) was
-- updated instead and loads into fcc_broadband_coverage, so
-- fcc_broadband_availability was never populated and is not referenced by
-- any query or ingestor.

DROP TABLE IF EXISTS fcc_broadband_availability;
