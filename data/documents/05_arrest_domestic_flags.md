# Definitions: Arrest and Domestic Flags

**The `arrest` flag** is set to true when an arrest was made in direct connection with the
reported incident, either at the scene or as a subsequent result of the investigation, at
the time the record was last updated in the source system. It is a binary operational flag,
not a legal outcome indicator — it does not mean the arrested individual was charged,
prosecuted, or convicted, and it does not distinguish between an arrest of the offender
versus, in rare cases, another involved party. Some incidents show a delayed transition
from `arrest = false` to `arrest = true` as an investigation resolves after the incident
date, which is one reason arrest-rate statistics for very recent time periods are less
reliable than for periods with several months of settling time.

**The `domestic` flag** indicates the incident was classified as domestic-related under the
Illinois Domestic Violence Act of 1986, which defines "domestic relationship" broadly:
spouses or former spouses, family members, people who share or formerly shared a
residence, people with a child in common, people in a current or former dating
relationship, and people with disabilities and their caregivers. This is a substantially
broader definition than "intimate partner violence" alone, and the flag can apply across
many offense types (battery, criminal damage, harassment, etc.), not just violent crime
categories.

Both flags are set by the reporting officer or subsequent case update and are therefore
subject to the same classification-consistency caveats as the primary offense type: they
reflect a point-in-time determination within a specific legal and departmental framework,
not an independently verified ground truth.
