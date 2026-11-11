from pathlib import Path
import hashlib
import json
import subprocess

tested = "b171ee291d98b86c137e2e02093fc181bd96db52"
tested_base = "adeddc9149b97c21e595e743c9875d84e805eece"
base = "041a9bed1f3041647036ea36ef3e67a6e0cd12a5"
head = "4afe199f0bb39abafe3bb2e46a8ac91dc6332207"
claim = "8e8b1353f535d3158fbc00588e46bc5b0d7bcbc3"

def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()

assert git("rev-parse", "HEAD") == head
assert git("rev-parse", "HEAD^") == claim
assert git("rev-parse", claim + "^") == base
assert git("diff", "--name-only", tested_base, base).splitlines() == ["docs/ROADMAP.md"]
assert git("diff", "--name-only", tested, head).splitlines() == ["docs/ROADMAP.md", "docs/STATUS.md"]
assert git("diff", "--name-only", base, head).splitlines() == [
    "crates/engine/src/tools/packet_tools.rs",
    "crates/engine/tests/packet_evidence_completeness.rs",
    "docs/ROADMAP.md",
    "docs/STATUS.md",
]
identities = {}
for name in ["crates/engine/src/tools/packet_tools.rs", "crates/engine/tests/packet_evidence_completeness.rs"]:
    original = subprocess.check_output(["git", "show", tested + ":" + name])
    actual = Path(name).read_bytes()
    assert actual == original, name
    identities[name] = hashlib.sha256(actual).hexdigest()
print(json.dumps({"head": head, "tested": tested, "base": base, "claim_parent": claim,
                  "only_docs_changed_since_tested": True, "sha256": identities}, sort_keys=True))
