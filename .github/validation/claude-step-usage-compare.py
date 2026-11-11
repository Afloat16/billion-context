import json
from pathlib import Path
import re
import subprocess

source = Path("src/services/worker/ClaudeProvider.ts")
test = "tests/worker/claude-provider-step-usage.test.ts"
base = "51ecfbe540b634f77eaa52e469b9bedadfd6b1e0"
fixed = source.read_bytes()
def run(phase, expected):
    result = subprocess.run(["bun", "test", "--timeout", "30000", test], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    print(output, flush=True)
    passed = re.findall(r"(?m)^\s*(\d+) pass\s*$", output)
    failed = re.findall(r"(?m)^\s*(\d+) fail\s*$", output)
    assert len(passed) == len(failed) == 1, (phase, result.returncode, passed, failed)
    actual = (int(passed[0]), int(failed[0]))
    assert actual == expected, (phase, actual, expected)
    assert (result.returncode == 0) == (expected[1] == 0), (phase, result.returncode)
    if phase == "original":
        names = [
            "carries a thinking frame usage into the text block without charging it twice",
            "stores every text block while persisting the step cost only once",
            "recognizes a repeated step even after a different step has reported usage",
            "does not need a result frame to avoid duplicate accounting on an interrupted stream",
            "retains finalized gateway backfill when repeated frames report zero input",
        ]
        failures = [line for line in output.splitlines() if "(fail)" in line]
        assert len(failures) == len(names), failures
        for name in names:
            assert any(name in line for line in failures), (name, failures)
    print("CLAUDE_STEP_USAGE_REGRESSIONS " + json.dumps(dict(phase=phase, passed=actual[0], failed=actual[1])), flush=True)

try:
    source.write_bytes(subprocess.check_output(["git", "show", base + ":src/services/worker/ClaudeProvider.ts"]))
    run("original", (5, 5))
finally:
    source.write_bytes(fixed)
subprocess.run(["git", "diff", "--exit-code", "--", str(source)], check=True)
run("fixed", (10, 0))
