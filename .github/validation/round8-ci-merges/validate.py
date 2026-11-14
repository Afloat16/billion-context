import hashlib, json, os, pathlib, re, subprocess, sys, traceback

manifest=json.loads(pathlib.Path(sys.argv[1]).read_text())
entry=next(x for x in manifest if str(x["number"])==sys.argv[2])
out=pathlib.Path(os.environ["RUNNER_TEMP"])/("billion-ci-merge-"+sys.argv[2])
out.mkdir(exist_ok=True)
report={"pr":entry["number"],"source":entry["source"],"parent":entry["parent"],"upstream":entry["upstream"],"commands":[]}
def run(args, name, expected=0):
    result=subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (out/(name+".log")).write_text(result.stdout)
    print("COMMAND "+name+" EXIT "+str(result.returncode), flush=True)
    print(result.stdout[-16000:], flush=True)
    report["commands"].append({"name":name,"argv":args,"exit":result.returncode})
    if result.returncode!=expected:
        raise AssertionError(name+": unexpected exit "+str(result.returncode))
    return result.stdout
def git(*args):
    return subprocess.check_output(["git",*args],text=True).strip()
def tap(name, files, passed, failed=0):
    args=["node","--import","./tests/preload-storage-baseline.mjs","--import","./tests/preload-test-env.mjs","--import","./tests/preload-zone-slot.mjs","--import","tsx","--test","--test-concurrency=1",*files]
    text=run(args,name,1 if failed else 0)
    counts={}
    for key in ["tests","pass","fail","cancelled","skipped"]:
        matches=re.findall(r"^# "+key+r" (\d+)\s*$",text,re.M)
        if not matches: raise AssertionError(name+": absent TAP "+key)
        counts[key]=int(matches[-1])
    assert counts["pass"]==passed and counts["fail"]==failed and counts["skipped"]==0 and counts["cancelled"]==0, counts
    report[name]=counts
    return text

notice=pathlib.Path("tests/notice-registry.test.ts")
original=None
try:
    assert git("rev-parse","HEAD")==entry["source"]
    assert git("show","-s","--format=%P","HEAD").split()==[entry["parent"],entry["upstream"]]
    changed=git("diff","--name-only",entry["upstream"],"HEAD").splitlines()
    assert sorted(changed)==sorted(f["path"] for f in entry["files"]), changed
    hashes={}
    for f in entry["files"]:
        assert git("rev-parse","HEAD:"+f["path"])==f["sha"]
        assert git("rev-parse",entry["parent"]+":"+f["path"])==f["sha"]
        hashes[f["path"]]=hashlib.sha256(pathlib.Path(f["path"]).read_bytes()).hexdigest()
    report["feature_sha256"]=hashes
    report["node"]=run(["node","--version"],"node-version").strip()
    report["npm"]=run(["npm","--version"],"npm-version").strip()
    run(["npm","ci","--ignore-scripts","--no-fund","--no-audit"],"install")
    run(["npm","run","typecheck"],"typecheck")
    run(["npm","run","build"],"build")
    run(["npm","run","check:unused-exports"],"unused-exports")
    run(["npm","run","check:test-import-graph"],"test-import-graph")
    run(["git","diff","--check",entry["upstream"],"HEAD"],"diff-check")
    tap("feature-and-adjacent",[entry["featureTest"],"tests/pi-inline.test.ts","tests/inline-streaming.test.ts"],entry["featureCount"]+8)
    original=notice.read_bytes()
    prior=subprocess.check_output(["git","show",entry["parent"]+":tests/notice-registry.test.ts"])
    assert prior!=original
    notice.write_bytes(prior)
    baseline=tap("notice-parent",["tests/notice-registry.test.ts"],3,2)
    assert "storage-sqlite-default" in baseline and "ERR_ASSERTION" in baseline
    notice.write_bytes(original)
    tap("notice-restored",["tests/notice-registry.test.ts"],5)
    assert notice.read_bytes()==original
    for f,h in hashes.items(): assert hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest()==h
    run(["git","diff","--exit-code"],"source-unchanged")
    report["status"]="passed"
except BaseException as e:
    report["status"]="failed"
    report["error"]=str(e)
    traceback.print_exc()
finally:
    if original is not None: notice.write_bytes(original)
    report["tracked_clean"]=git("diff","--name-only")==""
    (out/"report.json").write_text(json.dumps(report,indent=2))
    print("VALIDATION_REPORT "+json.dumps(report),flush=True)
if report["status"]!="passed": sys.exit(1)
