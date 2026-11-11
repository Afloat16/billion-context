import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys

root = Path.cwd()
capture = root / "synthetic-large.har"
entry = {
    "startedDateTime": "2026-01-01T00:00:00.000Z",
    "time": 12.5,
    "_resourceType": "fetch",
    "serverIPAddress": "192.0.2.10",
    "request": {
        "method": "POST",
        "url": "",
        "httpVersion": "HTTP/2",
        "headers": [{"name": f"X-Synthetic-{i}", "value": "v" * 64} for i in range(12)],
        "cookies": [{"name": "synthetic", "value": "fixture"}],
        "postData": {"mimeType": "application/json", "text": "p" * 512},
        "bodySize": 512,
    },
    "response": {
        "status": 200,
        "statusText": "OK",
        "httpVersion": "HTTP/2",
        "headers": [{"name": "Content-Type", "value": "application/json"}],
        "cookies": [],
        "content": {"size": 4096, "mimeType": "application/json", "text": "r" * 4096},
        "bodySize": 4096,
    },
    "timings": {"wait": 10, "receive": 2.5, "ssl": -1},
}
with capture.open("w", encoding="utf-8") as output:
    output.write('{"log":{"version":"1.2","creator":{"name":"synthetic","version":"1"},"pages":[{},{},{}],"entries":[')
    for i in range(20_000):
        if i:
            output.write(",")
        entry["request"]["url"] = f"https://capture.example.test/items/{i}"
        output.write(json.dumps(entry, separators=(",", ":"), ensure_ascii=False))
    output.write("]}}")
print("HAR_FIXTURE " + json.dumps({"bytes": capture.stat().st_size, "entries": 20_000, "sha256": hashlib.sha256(capture.read_bytes()).hexdigest()}), flush=True)
cpu = min(os.sched_getaffinity(0))
print("HAR_ENV " + json.dumps({
    "cpu": cpu,
    "rustc": subprocess.check_output(["rustc", "+1.99.0", "--version"], text=True).strip(),
    "uname": subprocess.check_output(["uname", "-a"], text=True).strip(),
    "processor": next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("model name")), ""),
}), flush=True)
records = []
for maximum in [0, 50, 5000]:
    expected = None
    for repetition in range(3):
        for variant in ["base", "fixed"]:
            executable = root / variant / "target/release/examples/har_budget_probe"
            result = subprocess.run(["taskset", "-c", str(cpu), "/usr/bin/time", "-v", str(executable), str(capture), str(maximum)], capture_output=True, check=True)
            log = result.stderr.decode()
            duration = int(re.search(r"HAR_PARSE_ELAPSED_NS=(\d+)", log).group(1))
            rss = int(re.search(r"Maximum resident set size \(kbytes\): (\d+)", log).group(1))
            digest = hashlib.sha256(result.stdout).hexdigest()
            identity = (len(result.stdout), digest)
            if expected is None:
                expected = identity
            assert identity == expected, (maximum, variant, identity, expected)
            record = {"limit": maximum, "variant": variant, "repetition": repetition + 1, "elapsed_ms": duration / 1e6, "max_rss_kib": rss, "output_bytes": identity[0], "output_sha256": digest}
            records.append(record)
            print("HAR_MEASUREMENT " + json.dumps(record), flush=True)
summaries = []
for maximum in [0, 50, 5000]:
    summary = {"limit": maximum}
    for variant in ["base", "fixed"]:
        selected = [r for r in records if r["limit"] == maximum and r["variant"] == variant]
        summary[variant] = {"elapsed_ms": statistics.median(r["elapsed_ms"] for r in selected), "max_rss_kib": statistics.median(r["max_rss_kib"] for r in selected)}
    summary["rss_ratio"] = summary["fixed"]["max_rss_kib"] / summary["base"]["max_rss_kib"]
    summary["time_ratio"] = summary["fixed"]["elapsed_ms"] / summary["base"]["elapsed_ms"]
    summaries.append(summary)
    print("HAR_COMPARISON " + json.dumps(summary), flush=True)
Path("har-measurements.json").write_text(json.dumps({"measurements": records, "summary": summaries}, indent=2))
