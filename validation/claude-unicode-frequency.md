# Fixed-SHA Unicode frequency validation

This isolated branch only validates claude-mem revisions; it does not modify product code or use write credentials.

- Main 22d148e with the 19 regressions from b7ce631: the observed baseline is 11 failures and 8 passes. The first workflow guessed 12/7; its original log remains available at run 43023420421.
- Original fix b7ce631 with 21 regressions from 2dc9cc3: additionally inject a cleanup failure after actual SQLite insertion, then search through a second SessionSearch on the same connection. Expected: one failure exposes stale temporary indexed words.
- Atomic fix 2dc9cc3: all 21 regressions, the SQLite/search suites, root and viewer TypeScript checks and every shipped bundle must pass.

The main fixture stays pinned to the original 19 tests because the new cleanup fault deliberately reaches a field introduced by the fix. Expected-failure jobs retain all production assertions; they check the observed test counts and nonzero test exit status. The fix job requires exit zero.
