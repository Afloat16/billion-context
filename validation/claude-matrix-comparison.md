# Claude-mem PostgreSQL matrix comparison

This diagnostic branch uses the same two immutable source revisions as the
WebSocket comparison: upstream main `6b779c06796138aeb4b0ee2fa7dbd25912e4f7fb`
and telemetry PR head `a9f5550fbc660ad105444b17e479e1a03e4eb437`.

The workflow checks out Afloat16/claude-mem with persisted Git credentials
disabled and read-only repository permissions. Each job receives its own
PostgreSQL 16 service and fresh `sync_api_test` database. Bun 1.4.4, Node 20,
the repository/service dependency setup, My Work dependencies, and warmed
Chrome follow the upstream sync matrix job.

The primary acceptance command is the unchanged
`bun scripts/sync-matrix-e2e.ts`. Earlier unit suites from the upstream job
are not rerun here: this comparison intentionally starts each matrix from a
fresh database.

If that command fails, a second run uses a separate fresh database. Its only
source edit is to pass the local, middle, and hosted review descriptors and
fingerprints as the existing assertion's optional diagnostic argument. The
assertion and all test behavior remain in place. This diagnostic rerun cannot
override the original result: the job remains failed if the unchanged
acceptance command failed.

Logs are retained as artifacts for seven days. They contain this script's
synthetic fixture data; no production data or repository secrets are supplied.
A passing repeat is evidence for that run only, and does not change an
upstream failed check or prove a failure cannot recur.

This branch creates no product PR and does not count as a contribution.
