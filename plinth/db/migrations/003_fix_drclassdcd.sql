-- Fix typo: drclassddc → drclassdcd (matches the SSURGO WFS field name)
ALTER TABLE ssurgo_muaggatt RENAME COLUMN drclassddc TO drclassdcd;
