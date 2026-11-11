import hashlib, json, subprocess
from pathlib import Path
cases=json.loads(Path("bzip2-cases.json").read_text())
mismatches=[]
for item in cases:
    p=subprocess.run(["base/target/debug/examples/bzip2_probe"], input=json.dumps({"input":item["input"],"cap":item["cap"]}), capture_output=True, text=True, timeout=5)
    if p.returncode:
        actual={"kind":"process_error","status":p.returncode,"stderr":p.stderr[-1000:]}
    else:
        actual=json.loads(p.stdout)
    if actual != item["expected"]:
        mismatches.append({"name":item["name"],"expected":item["expected"]["kind"],"actual":actual.get("kind"),"expected_bytes":len(item["expected"].get("bytes",[])),"actual_bytes":len(actual.get("bytes",[])),"stderr":actual.get("stderr")})
print("BZ2_FIXED="+json.dumps({"cases":len(cases),"mismatches":mismatches,"inputs_sha256":hashlib.sha256(json.dumps(cases,sort_keys=True,separators=(",",":")).encode()).hexdigest()}))
assert not mismatches
