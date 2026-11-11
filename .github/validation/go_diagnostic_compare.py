"""Compare original/fixed Go diagnostics, full reports and three fresh-process RSS samples."""
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import time

BASE = "3ce1ce9f52077a53811be8a0309fdbe85b16b417"
SOURCE = Path("crates/formats/src/go.rs")
PROBE = Path("crates/formats/examples/go_buildinfo_diagnostic_probe.rs")
FAILURE = "found a pointer-encoded build information header but could not follow its version pointer"
root = Path(os.environ["GO_DIAGNOSTIC_FIXTURES"])
native = json.loads((root / "manifest.json").read_text())
cargo = ["cargo", "--config", 'profile.dev.package."*".opt-level=0']
records = []

def module(value):
    if value is None:
        return None
    return dict(path=value.get("Path", ""), version=value.get("Version", ""),
                sum=value.get("Sum") or None, replace=module(value.get("Replace")))

def rust_module(value):
    if value is None:
        return None
    return dict(path=value.get("path", ""), version=value.get("version", ""),
                sum=value.get("sum") or None, replace=rust_module(value.get("replace")))

def native_facts(report):
    info = report["buildinfo"]
    assert info and info["complete"]
    assert info["go_version"] == native["buildinfo"]["GoVersion"]
    assert info["path"] == native["buildinfo"]["Path"]
    assert rust_module(info["main"]) == module(native["buildinfo"]["Main"])
    assert list(map(rust_module, info["deps"])) == list(map(module, native["buildinfo"].get("Deps") or []))
    assert info["settings"] == [{"key": item["Key"], "value": item["Value"]} for item in native["buildinfo"]["Settings"]]
    found = {item["name"]: int(item["entry"], 16) for item in report["pclntab"]["functions"]}
    for name, address in native["symbols"].items():
        assert found[name] == address, (name, found.get(name), address)

def tests(phase):
    result = subprocess.run(cargo + ["test", "--locked", "-p", "craft-anything-formats",
                            "--test", "go_buildinfo_diagnostics", "--", "--nocapture"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(result.stdout, flush=True)
    matches = re.findall(r"test result: \w+\. (\d+) passed; (\d+) failed; (\d+) ignored;", result.stdout)
    expected = (2, 4, 0) if phase == "original" else (6, 0, 0)
    assert len(matches) == 1 and tuple(map(int, matches[0])) == expected, (phase, result.returncode, matches)
    assert result.returncode == (101 if phase == "original" else 0), (phase, result.returncode)
    print("GO_DIAGNOSTIC_REGRESSIONS " + json.dumps(dict(phase=phase, passed=expected[0], failed=expected[1], ignored=0)), flush=True)

def measure(phase):
    subprocess.run(cargo + ["build", "--release", "--locked", "-p", "craft-anything-formats",
                           "--example", "go_buildinfo_diagnostic_probe"], check=True)
    binary = Path("target/release/examples/go_buildinfo_diagnostic_probe").resolve()
    for name, count, runs in [("control", 0, 1), ("relocated-control", 0, 1), ("single-pointer", 1, 1), ("many-pointers", 262144, 3)]:
        for iteration in range(runs):
            output = root / f"{phase}-{name}-{iteration}.json"
            timing = root / f"{phase}-{name}-{iteration}.time"
            with output.open("wb") as stream:
                subprocess.run(["/usr/bin/time", "-f", "%M %e", "-o", str(timing),
                                str(binary), str(root / name)], stdout=stream, check=True)
            result = json.loads(output.read_text())
            native_facts(result["report"])
            if count == 0:
                expected = {}
            elif count == 1 or phase == "original":
                expected = {FAILURE: count}
            else:
                expected = {f"found {count} pointer-encoded build information headers but could not follow their version pointers (candidate probes in this scan)": 1}
            assert result["diagnostic_counts"] == expected, (phase, name, result["diagnostic_counts"])
            peak, elapsed = timing.read_text().split()
            canonical = json.dumps(result["report"], sort_keys=True, separators=(",", ":")).encode()
            record = dict(phase=phase, file=name, iteration=iteration, peak_rss_kib=int(peak),
                          elapsed_seconds=float(elapsed), report_sha256=hashlib.sha256(canonical).hexdigest(),
                          functions=len(result["report"]["pclntab"]["functions"]),
                          diagnostic_counts=result["diagnostic_counts"])
            records.append(record)
            print("GO_DIAGNOSTIC_PROCESS " + json.dumps(record, sort_keys=True), flush=True)
            if phase == "fixed":
                original = json.loads((root / f"original-{name}-{iteration}.json").read_text())
                assert result["report"] == original["report"], (name, iteration, "metadata report changed")
                if count <= 1:
                    assert result == original, (name, iteration, "ordinary diagnostics changed")
                original_probes = sum(original["diagnostic_counts"].values())
                represented_probes = 0 if count == 0 else count
                assert original_probes == represented_probes, (name, original_probes, represented_probes)

fixed = SOURCE.read_bytes()
original = subprocess.check_output(["git", "show", BASE + ":crates/formats/src/go.rs"])
try:
    SOURCE.write_bytes(original)
    tests("original")
    measure("original")
finally:
    SOURCE.write_bytes(fixed)
subprocess.run(["git", "diff", "--exit-code", "--", str(SOURCE)], check=True)
tests("fixed")
measure("fixed")
for phase in ("original", "fixed"):
    hashes = {record["report_sha256"] for record in records if record["phase"] == phase and record["file"] == "many-pointers"}
    assert len(hashes) == 1, (phase, hashes)
old = statistics.median(record["peak_rss_kib"] for record in records if record["phase"] == "original" and record["file"] == "many-pointers")
new = statistics.median(record["peak_rss_kib"] for record in records if record["phase"] == "fixed" and record["file"] == "many-pointers")
assert new < old * 0.8, ("measured RSS improvement must be meaningful", old, new)
summary = dict(candidate_region_bytes=8388608, candidate_probes=262144, processes=len(records),
               stress_processes_per_version=3, original_median_peak_rss_kib=old,
               fixed_median_peak_rss_kib=new, reduction_percent=(1 - new / old) * 100,
               metadata_and_functions_identical=True,
               ordinary_complete_reports_identical=True,
               diagnostic_meaning_and_probe_counts_preserved=True,
               compiler_environment={key: os.environ.get(key) for key in
                   ("CARGO_PROFILE_RELEASE_LTO", "CARGO_PROFILE_RELEASE_CODEGEN_UNITS", "CARGO_PROFILE_RELEASE_DEBUG")},
               records=records)
(root / "performance.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
print("GO_DIAGNOSTIC_MEASUREMENT " + json.dumps(summary, sort_keys=True), flush=True)
