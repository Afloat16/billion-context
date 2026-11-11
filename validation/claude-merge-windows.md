# Windows acceptance comparison for claude-mem PR #5990

This branch checks out the fixed upstream main commit
`6b779c06796138aeb4b0ee2fa7dbd25912e4f7fb` and PR commit
`cb6d2ef0bc0c954d8d5bbda29489bcbe93176f65` in separate Windows 2022 jobs.
Node 22 and Bun 1.4.4 match the failed upstream job's actual versions.

After the repository's ordinary dependency installation and full build, it
runs the unchanged eight-file deep-search subprocess/release acceptance
command from `.github/workflows/windows.yml`. Earlier unrelated Windows
acceptance suites are not rerun here. Neither test code nor timeouts are
modified; the failing test retains its own explicit 60,000 ms timeout even
though the suite's default timeout is 120,000 ms.

The upstream job
https://github.com/thedotmack/claude-mem/actions/runs/43019056633/job/130517350923
built successfully, then reported 37 passing tests, one failure and one
unhandled error in this step. The host-death test exceeded 60,000 ms while
preparing/exercising its 32,000-row native SQLite fixture and reported
`Host exited before spawning`.

This comparison records actual baseline/head outcomes. A passing repeat does
not turn the original failed check green or establish why it failed. No
repository secrets, production data, product-branch changes, or new product
PR are involved.
