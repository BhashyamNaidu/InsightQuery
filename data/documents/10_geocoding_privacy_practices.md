# Location Privacy: Why Addresses Are Block-Level

Chicago's public crime dataset intentionally reports incident locations at the block level
(e.g., "025XX W DIVISION ST") rather than as an exact street address, and the accompanying
latitude/longitude coordinates are correspondingly generalized to correspond to that
blocked address rather than the true precise location.

This is a deliberate privacy control, applied consistently across all offense categories
in the public dataset (not selectively to sensitive categories, which would itself leak
information by omission). The rationale is twofold: it reduces the risk of publicly
identifying a specific residence or business as the site of a crime — which could expose
victims to secondary harm, stigmatize a specific address, or affect property values based
on a single incident — while still preserving enough geographic precision for legitimate
public safety analysis at the beat, district, ward, and community-area levels.

The practical consequence for analysis is that point-level or address-level spatial
queries (e.g., "which exact building had the most incidents") are not reliable, because
many distinct real addresses within the same block collapse to the same reported
coordinate. Aggregation at the block level, beat level, or higher (district, community
area) is the appropriate granularity for this dataset; treating the published
latitude/longitude as survey-grade precise location data will overstate spatial precision
the source data does not actually have.

This practice is consistent with open-data privacy guidance used by many U.S. municipal
open-data portals publishing incident-level public safety data, which generally recommend
either spatial generalization (as Chicago does) or aggregation into pre-defined zones
before publication.
