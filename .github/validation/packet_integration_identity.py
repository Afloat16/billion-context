from pathlib import Path
import hashlib
import json
import subprocess

tested = "b171ee291d98b86c137e2e02093fc181bd96db52"
tested_base = "adeddc9149b97c21e595e743c9875d84e805eece"
base = "06342656204c5ef25d145ec632468914d2a2982e"
head = "46c531c9d21c2dab35f2ae62d22c72786b931ea2"
claim = "0b91e68e594cb87ad5cfb852d815d42725c9e061"

def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()

def parents(ref):
    header = git("cat-file", "-p", ref).split("\n\n", 1)[0]
    return [line[7:] for line in header.splitlines() if line.startswith("parent ")]

assert git("rev-parse", "HEAD") == head
assert parents(head) == [claim]
assert parents(claim) == [base]
assert git("diff", "--name-only", tested_base, base).splitlines() == ["crates/formats/src/codesign.rs", "docs/ROADMAP.md"]
assert git("diff", "--name-only", tested, head).splitlines() == ["crates/formats/src/codesign.rs", "docs/ROADMAP.md", "docs/STATUS.md"]
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
                  "packet_change_matches_tested": True, "upstream_product_delta": ["crates/formats/src/codesign.rs"], "sha256": identities}, sort_keys=True))
