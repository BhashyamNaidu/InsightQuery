-- Re-run after migrations (or after creating/replacing tables) to guarantee the
-- readonly role can SELECT from exactly the tables the NL-to-SQL pipeline is
-- allowed to touch, and nothing else.
GRANT SELECT ON crimes, iucr_codes, police_districts, community_areas
    TO insightquery_readonly;
