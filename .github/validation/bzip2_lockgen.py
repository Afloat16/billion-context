import difflib, hashlib, json, subprocess, tomllib
from pathlib import Path
base=Path("base")
before=(base/"Cargo.lock").read_text()
old=tomllib.loads(before)
(base/"crates/formats/src/decompress.rs").write_text(Path("validation/.github/validation/bzip2_candidate.rs").read_text())
(base/"crates/formats/Cargo.toml").write_text(Path("validation/.github/validation/bzip2_candidate_manifest.toml").read_text())
with open("bzip2-metadata.json","w") as output:
    subprocess.run(["cargo","+1.99.0","metadata","--format-version","1"],cwd=base,stdout=output,check=True,timeout=300)
after=(base/"Cargo.lock").read_text()
new=tomllib.loads(after)
key=lambda p:(p["name"],p["version"],p.get("source",""))
oldkeys={key(p) for p in old["package"]}
newkeys={key(p) for p in new["package"]}
removed=sorted(oldkeys-newkeys); added=sorted(newkeys-oldkeys)
assert {p[0] for p in removed} == {"bzip2-rs", "tinyvec"}, removed
assert {p[0] for p in added} == {"bzip2","libbz2-rs-sys"}, added
metadata=json.loads(Path("bzip2-metadata.json").read_text())
active={n["id"] for n in metadata["resolve"]["nodes"]}
active_names={p["name"] for p in metadata["packages"] if p["id"] in active}
assert "libbz2-rs-sys" in active_names and "bzip2-sys" not in active_names
oldlines=before.splitlines(keepends=True); newlines=after.splitlines(keepends=True)
edits=[{"start":a,"end":b,"lines":newlines[c:d]} for tag,a,b,c,d in difflib.SequenceMatcher(a=oldlines,b=newlines,autojunk=False).get_opcodes() if tag!="equal"]
print("BZ2_DEPENDENCIES="+json.dumps({"removed":removed,"added":added,"active_native_c_backend":False}))
print("BZ2_LOCK_PATCH="+json.dumps({"old_sha256":hashlib.sha256(before.encode()).hexdigest(),"new_sha256":hashlib.sha256(after.encode()).hexdigest(),"new_bytes":len(after.encode()),"edits":edits}))
subprocess.run(["cargo","+1.99.0","fmt","--all"],cwd=base,check=True)
paths=["crates/formats/src/decompress.rs","crates/formats/tests/bzip2_members.rs","crates/formats/Cargo.toml"]
print("BZ2_FORMATTED_FILES="+json.dumps({p:(base/p).read_text() for p in paths}))
