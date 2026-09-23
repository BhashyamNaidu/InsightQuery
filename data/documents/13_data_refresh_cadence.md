# Data Refresh Cadence and Extraction Timing

The City of Chicago's open data portal updates the public crimes dataset on a daily
cadence, pulling from the CLEAR (Citizen Law Enforcement Analysis and Reporting) records
management system used operationally by the Chicago Police Department. Each daily refresh
both appends newly reported incidents and applies any updates to previously published
records — for example, an arrest made after the original report, or a reclassification
following investigation.

For any analytics platform built on a periodic snapshot (rather than a live daily sync)
of this data, it's important to record and communicate the **extraction timestamp** the
snapshot was pulled at, since:

1. Incidents from the last one to two weeks before extraction are systematically
   under-represented relative to their eventual final counts (see the reporting-lag
   discussion in the data-quality-limitations document), so trend lines showing an
   apparent "drop" in the most recent period are frequently a lag artifact rather than a
   real decline.
2. Any field that can be updated retroactively (arrest status, classification, geocoded
   location) reflects its value as of the extraction moment, not necessarily its final
   value.
3. Comparing two analyses pulled at different extraction times, even for the "same"
   historical period, can show small discrepancies purely because one snapshot captured
   more settled/corrected data than the other.

Best practice for a snapshot-based system is to clearly label the data's extraction/ingest
date wherever aggregate figures are presented, and to treat the most recent 2-3 weeks of
any snapshot with reduced confidence relative to older, settled periods.
