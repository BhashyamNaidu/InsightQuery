# IUCR Crime Classification Methodology

The Illinois Uniform Crime Reporting (IUCR) code is a four-digit code the Chicago Police
Department assigns to every reported incident to classify what kind of offense occurred.
IUCR codes are maintained by the Illinois State Police and mirror, but are not identical
to, the FBI's national Uniform Crime Reporting (UCR) categories.

Each IUCR code maps to exactly one "primary type" (a broad category such as THEFT,
BATTERY, or CRIMINAL DAMAGE) and one "secondary description" that narrows the offense
within that category (for example, THEFT's secondary descriptions include "$500 AND
UNDER," "OVER $500," "RETAIL THEFT," and "POCKET-PICKING"). The primary type is what
most dashboards and summary statistics group by, because secondary descriptions are far
more granular and inconsistent in how officers apply them across districts.

IUCR codes are grouped into ranges by offense family: codes in the 0100s are homicide,
0200s-0300s are sex offenses, 0400s-0500s are robbery, 0600s are battery, 0800s-0900s are
theft, and so on. A code's range is a useful sanity check when validating classification
data, but should not be treated as authoritative on its own — always defer to the
primary_type and secondary_desc fields.

Importantly, an IUCR code reflects the offense as classified at the time of reporting,
which may later be reduced, upgraded, or unfounded after investigation. The Chicago Police
Department's public dataset reflects the classification at time of data extraction and is
**not** the final adjudicated outcome of a case. Analysts comparing crime counts across
time periods should be aware that a small percentage of records are reclassified after
initial entry, which can cause minor retroactive shifts in historical monthly totals.

Each IUCR code also carries an "index crime" flag (see the companion document on index vs.
non-index crimes), which determines whether that offense counts toward the standardized,
cross-jurisdiction comparable subset of "Part I" crimes used in national crime-rate
comparisons.
