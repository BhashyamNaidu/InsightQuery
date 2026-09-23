# Known Data Quality Limitations of the Chicago Crime Dataset

The City of Chicago publishes reported incidents from its CLEAR (Citizen Law Enforcement
Analysis and Reporting) system, refreshed daily. The city's own data dictionary carries an
explicit disclaimer that matters for any analysis built on top of it: the data **has not
been reviewed or approved by the Chicago Police Department** before publication and should
be considered preliminary. Several categories of limitation follow from that.

**Reporting lag and retroactive correction.** A crime that occurred on a given date may not
appear in the dataset until days or weeks later, and classification, location, or arrest
fields can be corrected retroactively as an investigation proceeds. Aggregations over the
most recent 1-2 weeks of data are especially likely to undercount relative to the final
totals for that period once corrections settle.

**Geographic precision is intentionally reduced.** Addresses are truncated to the nearest
block (e.g., "007XX N STATE ST") rather than published as exact street addresses, and
latitude/longitude coordinates are correspondingly generalized. This is a deliberate
privacy protection, particularly relevant for sensitive offense categories, and means
block-level or point-level spatial analysis carries inherent locational uncertainty of
roughly half a block.

**Not every record has a valid location.** A small percentage of records have null or
placeholder latitude/longitude (sometimes defaulting to a jurisdiction centroid) when a
precise location could not be geocoded. Any spatial analysis should treat missing
coordinates as missing, not as "zero," and should report what fraction of records were
excluded.

**Arrest and domestic flags reflect the incident record, not the final case outcome.** An
`arrest = true` flag means an arrest was made in connection with the incident, not that a
conviction resulted. Similarly, `domestic = true` is an initial classification under the
Illinois Domestic Violence Act's broad relationship definitions.

**The dataset excludes categories that are cleared/unfounded before entry**, and juvenile
offender records are handled with additional restrictions per state law. Any published
count is therefore best read as "reported incidents matching this criteria," not as a
complete census of all crime that occurred.
