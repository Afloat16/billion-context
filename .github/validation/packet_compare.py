import os
from pathlib import Path
import re
import subprocess

base = "adeddc9149b97c21e595e743c9875d84e805eece"
head = "b171ee291d98b86c137e2e02093fc181bd96db52"
source = Path("crates/engine/src/tools/packet_tools.rs")
fixed = source.read_bytes()
original = subprocess.check_output(["git", "show", base + ":" + str(source)])
native = Path("crates/engine/tests/packet_native_validation.rs")
native.write_bytes((Path(os.environ["GITHUB_WORKSPACE"]) / "validation/.github/validation/packet_native_validation.rs").read_bytes())
config = ["cargo", "--config", 'profile.dev.package."*".opt-level=0', "test", "--locked", "-p", "craft-anything-engine"]

def check(label, target, passed, failed):
    result = subprocess.run(config + ["--test", target, "--", "--test-threads=2"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print("=== " + label + " ===", flush=True)
    print(result.stdout, flush=True)
    summary = re.findall(r"test result: (?:ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored", result.stdout)
    assert summary == [(str(passed), str(failed), "0")], (label, summary)
    assert (result.returncode == 0) == (failed == 0), (label, result.returncode)
    print("VERIFIED " + label + ": " + str(passed) + " passed / " + str(failed) + " failed", flush=True)

try:
    source.write_bytes(original)
    check("baseline " + base + " focused", "packet_evidence_completeness", 3, 10)
    check("baseline " + base + " native", "packet_native_validation", 2, 3)
    source.write_bytes(fixed)
    check("fixed " + head + " focused", "packet_evidence_completeness", 13, 0)
    check("fixed " + head + " native", "packet_native_validation", 5, 0)
finally:
    source.write_bytes(fixed)
    native.unlink()
assert subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() == head
subprocess.run(["git", "diff", "--exit-code"], check=True)
