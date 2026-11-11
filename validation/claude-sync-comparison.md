# Sync-hub acceptance comparison for telemetry aggregation

This branch is a diagnostic run for upstream PR #5994. It is not an additional
product change or pull request.

## Revisions

- Baseline: `6b779c06796138aeb4b0ee2fa7dbd25912e4f7fb` (upstream main).
- Telemetry change: `a9f5550fbc660ad105444b17e479e1a03e4eb437`.
- Workflow: `.github/workflows/claude-sync-comparison.yml`.

The workflow checks out each exact revision on an `ubuntu-latest` runner,
installs Bun 1.4.4, and runs the sync-hub package's frozen dependency installation
and unchanged test commands. No production code, test assertions, timers, or
test fixtures are modified.

## Commands

From `services/sync-hub`:

```sh
bun install --frozen-lockfile
bun run test
bun run test:ws
```

The main suite runs once per revision. The WebSocket command runs five times
in separate test invocations per revision; every attempt is logged, and the
job fails if any attempt fails. This small repetition targets a specific
timing failure rather than treating one passing retry as proof of correctness.

## Failure being investigated

The upstream job
https://github.com/thedotmack/claude-mem/actions/runs/43016097891/job/130507437427
passed all 146 main-suite tests and 11 of 12 WebSocket tests. The remaining
test, `closes a quiet socket at its deadline through the alarm, without a push`,
failed at `test/ws.test.ts:245`: `getAlarm()` returned `null` instead of the
expected deadline. The test schedules its deadline 200 ms after `Date.now()`,
then reads that alarm before its later 250 ms wait. That timing relationship
is a lead to investigate; it does not establish the cause of this failure.

The other failed upstream job, the PostgreSQL matrix test at
https://github.com/thedotmack/claude-mem/actions/runs/43016097891/job/130507437610,
is separate and is not exercised by this workflow.

## Interpreting results

- The same assertion failing on both revisions demonstrates that this failure
  can occur on the baseline under this comparison's configuration.
- A failure on the change with a passing baseline requires further
  investigation; this workflow alone does not identify the cause.
- Passing all attempts establishes only that these particular runs passed.
  It does not make the upstream red check green, prove the failure impossible,
  or justify calling it a baseline defect.

Keep the upstream check status and both revisions' actual logs when reporting
the outcome.

## Execution host

This isolated validation branch is hosted in Afloat16/billion-context. The
workflow explicitly checks out Afloat16/claude-mem at the two fixed revisions,
with read-only repository permissions and persisted Git credentials disabled.
It uses no repository secrets and makes no changes to either product's branches.
