from pathlib import Path
import json, os, subprocess, sys

phase=sys.argv[1]
assert phase in ("baseline","fixed")
root=Path(os.environ["RUNNER_TEMP"])/"arm32-native"
cases=json.loads((root/"cases.json").read_text())
program=Path("base/target/debug/examples/arm_core_probe").resolve()
run=subprocess.run([str(program),*[str(root/case["file"]) for case in cases]],text=True,capture_output=True,timeout=60)
assert run.returncode == 0, (run.returncode,run.stderr[-3000:])
rows=[json.loads(line) for line in run.stdout.splitlines() if line.startswith("{")]
assert len(rows) == 4, run.stdout
by_file={row["file"]:row for row in rows}
mismatches=[]
for case in cases:
    row=by_file[case["file"]]
    assert row["bits"] == 32, row
    expected=case["registers"].copy()
    # QEMU 8.2.2's ARM core writer stores r0 in this final Linux slot.
    # GDB independently supplies the other 17 registers.
    expected["orig_r0"]=expected["r0"]
    tool={r["name"]:int(r["value"],0) for r in row["tool_threads"][0]["registers"]}
    issues=[]
    if row["registers"] != expected: issues.append("parser registers")
    if tool != expected: issues.append("evidence registers")
    if row["pc"] != case["expected_pc"]: issues.append("parser PC")
    if row["tool_pc"] != hex(case["expected_pc"]): issues.append("evidence PC")
    if " at "+hex(case["expected_pc"]) not in row["summary"]: issues.append("summary PC")
    if issues: mismatches.append({"name":case["name"],"fields":issues})
report={"phase":phase,"cases":len(cases),"mismatches":mismatches,"independent_debugger_registers_per_case":17,"producer_defined_original_r0_per_case":1}
print("ARM_CORE_COMPARISON="+json.dumps(report),flush=True)
assert {item["name"] for item in mismatches} == ({case["name"] for case in cases} if phase == "baseline" else set()), report
