from pathlib import Path
import subprocess

MEASURED = "6bafba62e745cd3e5fbebb2baf085fffee62ed7b"
UNCHANGED = [
    "crates/formats/src/sqlite.rs", "crates/engine/src/tools/database_tools.rs",
    "crates/testkit/src/sqlite.rs", "crates/formats/tests/sqlite_schema_completeness.rs",
    "Cargo.toml", "Cargo.lock", "crates/formats/Cargo.toml",
    "crates/engine/Cargo.toml", "crates/testkit/Cargo.toml",
]
for path in UNCHANGED:
    previous = subprocess.check_output(["git", "show", f"{MEASURED}:{path}"])
    assert Path(path).read_bytes() == previous, path
    print(f"Identical to measured source {MEASURED}: {path}", flush=True)
test = "crates/engine/tests/sqlite_schema_completeness.rs"
previous = subprocess.check_output(["git", "show", f"{MEASURED}:{test}"], text=True)
old = '            .err()\n            .expect("an unknown table must return an error");'
new = '            .expect_err("an unknown table must return an error");'
assert previous.count(old) == 1
assert Path(test).read_text() == previous.replace(old, new)
print("The sole regression change uses Result::expect_err as required by strict Clippy.", flush=True)
subprocess.run(["git", "diff", "--exit-code"], check=True)
