# Unicode vocabulary baseline probe

The source checkout is `636ed78d5590792e872e1ce9bb98c747e3ffa694` in
Afloat16/claude-mem. It adds only a diagnostic test to upstream main
`22d148ea6f34b86ea9a6e0911c7a7a0c71431b31`; production source is unchanged.

Bun 1.4.4 runs native SQLite FTS5 oracle cases for remove_diacritics 0, 1 and 2.
The production regressions create real SessionStore data and query through
SearchManager.search using its SQLite path. They compare keyword, short
three-term and long (over 600 code points) queries for ASCII, Latin-accented,
Greek, Cyrillic and Vietnamese words, across observations and summaries.
Foreign-project copies must remain excluded.

These are synthetic fixtures, no model/provider calls or live user data.
A failed production regression is a candidate reproduction, not evidence
that a fix exists. No product PR has been opened for this probe.
