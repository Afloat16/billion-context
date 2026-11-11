from pathlib import Path
import hashlib
import json
import subprocess

tested = "46c531c9d21c2dab35f2ae62d22c72786b931ea2"
tested_base = "06342656204c5ef25d145ec632468914d2a2982e"
base = "86d047cbc5368ca595c83e045893fb39c7f3f7f8"
head = "8ede68574392af1cf9123a4aec179b5557689964"
claim = "ae853665d386f2a3def39f49f9c00eeba13d8d28"
upstream_files = ["crates/ai/src/cli_agents/adapters.rs","crates/ai/src/cli_agents/adapters/opencode.rs","crates/ai/src/cli_agents/mod.rs","crates/ai/src/rebuild/tests.rs","crates/ai/src/tests.rs","docs/ROADMAP.md"]

def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()

def parents(ref):
    header = git("cat-file", "-p", ref).split("\n\n", 1)[0]
    return [line[7:] for line in header.splitlines() if line.startswith("parent ")]

assert git("rev-parse", "HEAD") == head
assert parents(head) == [claim]
assert parents(claim) == [base]
assert git("diff", "--name-only", tested_base, base).splitlines() == upstream_files
assert git("diff", "--name-only", tested, head).splitlines() == upstream_files
assert git("diff", "--name-only", base, head).splitlines() == [
    "crates/engine/src/tools/packet_tools.rs",
    "crates/engine/tests/packet_evidence_completeness.rs",
    "docs/ROADMAP.md",
    "docs/STATUS.md",
]
for name in upstream_files:
    if name == "docs/ROADMAP.md":
        continue
    assert name.startswith("crates/ai/src/"), name
    expected = subprocess.check_output(["git", "show", base + ":" + name])
    assert Path(name).read_bytes() == expected, name
identities = {}
for name in [
    "crates/engine/src/tools/packet_tools.rs",
    "crates/engine/tests/packet_evidence_completeness.rs",
    "Cargo.toml",
    "Cargo.lock",
    "crates/engine/Cargo.toml",
    "crates/formats/Cargo.toml",
    "crates/testkit/Cargo.toml",
]:
    expected = subprocess.check_output(["git", "show", tested + ":" + name])
    actual = Path(name).read_bytes()
    assert actual == expected, name
    identities[name] = hashlib.sha256(actual).hexdigest()
print(json.dumps({"head": head, "tested": tested, "base": base, "claim_parent": claim,
                  "upstream_files_inherited_exactly": upstream_files,
                  "entire_lower_layer_tree_unchanged": True,
                  "sha256": identities}, sort_keys=True))
