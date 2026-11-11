from pathlib import Path
import json, os, subprocess

root=Path(os.environ["RUNNER_TEMP"])/"elf-signal-native"
cases=json.loads((root/"cases.json").read_text())
program=Path("base/target/debug/examples/core_signal_probe").resolve()
run=subprocess.run([str(program),*[str(root/c["file"]) for c in cases]],text=True,capture_output=True,timeout=60)
assert run.returncode == 0, (run.returncode,run.stderr[-3000:])
actual=[json.loads(line) for line in run.stdout.splitlines() if line.startswith("{")]
assert len(actual) == len(cases), run.stdout[-5000:]
by_file={row["file"]:row for row in actual}
mismatches=[]
for case in cases:
    row=by_file[case["file"]]
    expected=case["native"]
    issues=[]
    for field in ("signal","tool_signal"):
        signal=row[field]
        assert signal is not None, (case["name"],row)
        for key in ("signo","code","errno"):
            if signal[key] != expected[key]: issues.append(field+"."+key)
        if signal["fault_addr"] != case["expected_fault"]: issues.append(field+".fault_addr")
        marker=case["meaning_contains"]
        if marker and marker not in signal["meaning"].lower(): issues.append(field+".meaning")
    if case["meaning_contains"] and case["meaning_contains"] not in row["summary"].lower(): issues.append("summary")
    if case["expected_fault"] is None and row["fault_location"] is not None: issues.append("fault_location")
    if issues: mismatches.append({"name":case["name"],"fields":issues,"signal":row["signal"]})
report={"cases":len(cases),"mismatches":mismatches,"controls":len(cases)-len(mismatches)}
print("NATIVE_CORE_BASELINE="+json.dumps(report),flush=True)
assert {item["name"] for item in mismatches} == {"kill-segv","raise-ill","queue-bus","timer-segv","kill-abrt"}, report
