import hashlib, json, subprocess, sys
from pathlib import Path
cases=json.loads(Path("zstd-checksum-cases.json").read_text())
probe=sys.argv[1]
result=subprocess.run([probe], input=json.dumps(cases), text=True, capture_output=True, check=True, timeout=90)
rows=json.loads(result.stdout)
assert len(rows)==len(cases)
failures=[]
for case,row in zip(cases,rows):
    if row != case["expected"]:
        failures.append({"name":case["name"],"expected":case["expected"]["status"],"actual":row["status"],"returned_bytes":len(row.get("bytes",[]))})
print("PRODUCTION_COMPARISON=" + json.dumps({"source":sys.argv[2],"cases":len(cases),"mismatches":failures,"output_sha256":hashlib.sha256(result.stdout.encode()).hexdigest()}))
if sys.argv[2]=="fixed":
    assert not failures, failures
else:
    assert failures and all(x["expected"]=="corrupt" and x["actual"]=="ok" for x in failures), failures
