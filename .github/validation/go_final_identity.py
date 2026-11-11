import hashlib
import json
from pathlib import Path
import subprocess

base = "3ce1ce9f52077a53811be8a0309fdbe85b16b417"
claim = "ace2048a1d6e9424bf5aa31e399119cabdb63659"
tested = "da3e2b157a5e0d9dfb98dafe2fe9646159719a4f"
final = "bfe391a2da3c36bb76af7256c8c0fbec15209d96"
def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()
def parents(commit):
    header = git("cat-file", "-p", commit).split("\n\n", 1)[0]
    return [line[7:] for line in header.splitlines() if line.startswith("parent ")]
assert git("rev-parse", "HEAD") == final
assert parents(final) == ["8779ef0f251418d1007e475590bb9cb7326d5ce6"]
assert parents("8779ef0f251418d1007e475590bb9cb7326d5ce6") == [tested]
assert parents(tested) == [claim]
assert parents(claim) == [base]
assert git("diff", "--name-only", base, claim).splitlines() == ["docs/ROADMAP.md"]
assert git("diff", "--name-only", tested, final).splitlines() == ["docs/ROADMAP.md", "docs/STATUS.md", "docs/pitfalls.md"]
assert git("diff", "--name-only", base, final).splitlines() == [
    "crates/formats/src/go.rs", "crates/formats/tests/go_buildinfo_diagnostics.rs",
    "docs/ROADMAP.md", "docs/STATUS.md", "docs/pitfalls.md",
]
subprocess.run(["git", "diff", "--exit-code", tested, final, "--", ".", ":!docs/ROADMAP.md", ":!docs/STATUS.md", ":!docs/pitfalls.md"], check=True)
paths = ["crates/formats/src/go.rs", "crates/formats/tests/go_buildinfo_diagnostics.rs",
         "Cargo.toml", "Cargo.lock", "crates/formats/Cargo.toml", "rust-toolchain.toml"]
hashes = {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in paths if Path(path).exists()}
roadmap = Path("docs/ROADMAP.md").read_text()
assert roadmap.count("- [x] Bound retained diagnostics for unreadable Go build information version pointers") == 1
assert "- [ ] Bound retained diagnostics for unreadable Go build information version pointers" not in roadmap
assert "70.2% lower median peak RSS" in roadmap
status = Path("docs/STATUS.md").read_text()
assert status.count("| Go build information diagnostics |") == 1
assert "47,504 → 14,160 KiB (70.2% lower)" in status
assert "43069839827" in status
assert "Zero bytes after an ELF program-header table were not free space." in Path("docs/pitfalls.md").read_text()
print("GO_FINAL_SOURCE_IDENTITY " + json.dumps(dict(base=base, claim=claim, tested=tested, final=final,
    claim_preceded_implementation=True, entire_non_documentation_tree_identical=True,
    final_changed_only=["docs/ROADMAP.md", "docs/STATUS.md", "docs/pitfalls.md"], hashes=hashes), sort_keys=True))
