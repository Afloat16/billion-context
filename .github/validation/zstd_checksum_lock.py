import json, re
from pathlib import Path
base=Path("Cargo.lock.original").read_text()
current=Path("Cargo.lock").read_text()
def packages(text):
    blocks=re.findall(r"(?ms)^\[\[package\]\]\n.*?(?=^\[\[package\]\]|\Z)",text)
    return {re.search(r'^name = "([^"]+)"',b,re.M).group(1)+"@"+re.search(r'^version = "([^"]+)"',b,re.M).group(1):b for b in blocks}
old,new=packages(base),packages(current)
added=set(new)-set(old)
changed={k for k in old.keys()&new.keys() if old[k]!=new[k]}
assert not (set(old)-set(new))
assert changed=={"ruzstd@0.9.1"},changed
assert len(added)==1 and next(iter(added)).startswith("twox-hash@"),added
print("LOCK_PATCH_JSON="+json.dumps({"ruzstd":new["ruzstd@0.9.1"],"added":[new[k] for k in sorted(added)],"lock_sha256":__import__("hashlib").sha256(current.encode()).hexdigest()}))
