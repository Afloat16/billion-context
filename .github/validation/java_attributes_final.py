import hashlib
import json
from pathlib import Path
import subprocess

BASE = "3ce1ce9f52077a53811be8a0309fdbe85b16b417"
CLAIM = "7d6576d35d9220de9e0fbd28be939ed1f05b1ef3"
INITIAL = "825c87b994a93491ec1a0ac8590828d8775ca14a"
TESTED = "44bf041627784d278917b1ef0e9aa3cd1332331b"
HEAD = "4fcec5dd79c07e2d3fd76557e05cad4da85f9bc9"
PRODUCT = [
    "crates/formats/src/java_class.rs",
    "crates/formats/tests/java_attribute_framing.rs",
    "crates/engine/src/tools/java_tools.rs",
    "crates/engine/tests/java_attribute_completeness.rs",
]
DOCS = ["docs/ROADMAP.md", "docs/STATUS.md"]

def git(*args):
    return subprocess.check_output(["git", *args])

def parent(commit):
    header = git("cat-file", "-p", commit).split(b"\n\n", 1)[0]
    parents = [line.split()[1].decode() for line in header.splitlines() if line.startswith(b"parent ")]
    assert len(parents) == 1, (commit, parents)
    return parents[0]

assert git("rev-parse", "HEAD").decode().strip() == HEAD
assert parent(HEAD) == TESTED
assert parent(TESTED) == INITIAL
assert parent(INITIAL) == CLAIM
assert parent(CLAIM) == BASE
assert git("diff", "--name-only", BASE, CLAIM).decode().splitlines() == ["docs/ROADMAP.md"]
assert sorted(git("diff", "--name-only", TESTED, HEAD).decode().splitlines()) == sorted(DOCS)
assert sorted(git("diff", "--name-only", BASE, HEAD).decode().splitlines()) == sorted(PRODUCT + DOCS)
claim = git("show", CLAIM + ":docs/ROADMAP.md").decode()
final = Path("docs/ROADMAP.md").read_text()
marker = "Preserve readable Java class and Code facts when an attribute table is truncated, stop at untrusted outer table boundaries, and report partial evidence instead of silent completeness."
assert "- [ ] " + marker in claim
assert "- [x] " + marker in final
hashes = {}
for path in PRODUCT + ["Cargo.toml", "Cargo.lock", "crates/formats/Cargo.toml", "crates/engine/Cargo.toml", "crates/testkit/Cargo.toml"]:
    contents = Path(path).read_bytes()
    assert contents == git("show", TESTED + ":" + path), path
    hashes[path] = hashlib.sha256(contents).hexdigest()
print(json.dumps(dict(head=HEAD, tested=TESTED, base=BASE, public_claim=CLAIM,
      documentation_only=True, entire_compiled_source_unchanged=True, sha256=hashes), sort_keys=True))
