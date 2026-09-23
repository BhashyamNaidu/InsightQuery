# FBI UCR Classification: Part I vs. Part II Offenses

The FBI's Uniform Crime Reporting (UCR) Program, which the Chicago Police Department
reports into, divides offenses into two broad tiers.

**Part I offenses** ("index crimes") are the eight offense categories the FBI considers
serious enough, and consistently reported enough, to serve as the national benchmark for
tracking crime trends: criminal homicide, forcible rape (criminal sexual assault),
robbery, aggravated assault, burglary, larceny-theft, motor vehicle theft, and arson. These
are the crimes most commonly cited in "crime rate" headlines and year-over-year comparison
statistics, precisely because their definitions are relatively stable and reporting
practices are more consistent across departments than for less serious offenses.

**Part II offenses** cover everything else: simple assault, fraud, forgery, vandalism,
weapons violations, drug offenses, vice offenses, and so on. Part II offenses are reported
based on arrests rather than every reported incident in the traditional national UCR
system, though Chicago's open dataset records every reported incident regardless of tier,
which is one reason the open dataset's totals are not directly comparable to the FBI's
official published UCR statistics for the same period.

In 2021, the national UCR Program formally transitioned to the National Incident-Based
Reporting System (NIBRS), which records more detail per incident (multiple offenses,
multiple victims) rather than a single "highest offense" per incident under the older
Summary Reporting System. Chicago's IUCR-based classification predates and is independent
of this transition, but analysts should be cautious when comparing Chicago's locally
reported figures to national NIBRS-era statistics, since the counting rules differ.

The `fbi_code` field in Chicago's crime data is a mapping from the local IUCR code to the
corresponding two-digit national UCR offense code, and is what allows (imperfect)
comparison to national crime statistics.
