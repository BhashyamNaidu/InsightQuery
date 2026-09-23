# Index Crimes vs. Non-Index Crimes

"Index crime" is a legacy term from the FBI's original Uniform Crime Reporting program,
referring to the set of offenses selected — originally in 1930 — as a standardized index
for tracking the nation's crime rate over time and comparing rates across jurisdictions.
The eight index offenses are identical to the "Part I" offenses described in the companion
FBI classification document: homicide, criminal sexual assault, robbery, aggravated
assault/battery, burglary, theft, motor vehicle theft, and arson.

In Chicago's IUCR-coded data, each offense code carries an `index_crime` flag marking
whether it belongs to this standardized set. The purpose of the distinction is
comparability: index crimes were chosen in part because they are serious enough to be
reliably reported to police (unlike, say, minor drug possession, which is uncovered mostly
through proactive enforcement rather than victim reporting), which makes trends in
index-crime rates a more defensible signal of actual changes in crime than trends in
offenses whose reporting is itself driven by enforcement intensity.

Non-index crimes are everything else — simple assault, weapons violations, deceptive
practice, vandalism, and dozens of other categories — which remain important for local
operational purposes (they're often the highest-volume categories) but are less suited to
cross-jurisdiction or long-horizon national comparison, precisely because how proactively a
department enforces and records them varies more than how a robbery or homicide gets
reported.

When building a "crime rate" summary intended to be compared against another city or
national benchmarks, restricting to `index_crime = true` offenses produces a more
defensible comparison than an all-offense total; when the goal is understanding total
local police workload or resident-facing incident volume, the all-offense total is more
appropriate.
