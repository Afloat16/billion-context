"""Run identical regressions against the fixed source and the original production files."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

BASE = "3ce1ce9f52077a53811be8a0309fdbe85b16b417"
PRODUCTION = ["crates/formats/src/java_class.rs", "crates/engine/src/tools/java_tools.rs"]
TESTS = [
    ("craft-anything-formats", "java_attribute_framing", 1, 8),
    ("craft-anything-engine", "java_attribute_completeness", 1, 6),
    ("craft-anything-engine", "java_attribute_native_validation", 2, 7),
]

def run(crate, target, expected_passed, expected_failed, phase):
    command = ["cargo", "--config", 'profile.dev.package."*".opt-level=0', "test", "--locked",
               "-p", crate, "--test", target, "--", "--nocapture"]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(result.stdout, flush=True)
    summary = re.findall(r"test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored;", result.stdout)
    assert len(summary) == 1, (phase, target, result.returncode, summary)
    label, passed, failed, ignored = summary[0]
    expected_code = 0 if expected_failed == 0 else 101
    assert (result.returncode, int(passed), int(failed), int(ignored)) == (expected_code, expected_passed, expected_failed, 0), (
        phase, target, result.returncode, summary, expected_passed, expected_failed)
    print("JAVA_ATTRIBUTE_COMPARISON " + json.dumps(dict(phase=phase, target=target, passed=int(passed),
          failed=int(failed), ignored=int(ignored), returncode=result.returncode), sort_keys=True), flush=True)

def main():
    copies = {path: Path(path).read_bytes() for path in PRODUCTION}
    try:
        for path in PRODUCTION:
            Path(path).write_bytes(subprocess.check_output(["git", "show", BASE + ":" + path]))
        for crate, target, passed, failed in TESTS:
            run(crate, target, passed, failed, "original")
    finally:
        for path, contents in copies.items():
            Path(path).write_bytes(contents)
    subprocess.run(["git", "diff", "--exit-code", "--", *PRODUCTION], check=True)
    for crate, target, passed, failed in TESTS:
        run(crate, target, passed + failed, 0, "fixed")

if __name__ == "__main__":
    main()
