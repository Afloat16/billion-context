"""Fixed-SHA CRC compatibility and real stored-member read benchmarks."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import statistics
import subprocess
import sys
import zipfile
import zlib

WORKSPACE = Path(os.environ["GITHUB_WORKSPACE"])
VALIDATION = WORKSPACE / "validation"
BASELINE = WORKSPACE / "baseline"
CANDIDATE = WORKSPACE / "candidate"
OUTPUT = WORKSPACE / "crc-results"
BASE_SHA = "7116cc6cb486ada87497de2568c6b6db5a2ea783"
FIX_SHA = "29eae51d4391e18f315c9f9fc3b86e4988f9b9a6"
LENGTHS = [0, 1, 2, 3, 4, 7, 8, 15, 16, 31, 32, 63, 64, 127, 128, 255, 256, 257,
           511, 512, 1023, 1024, 4095, 4096, 4097, 65535, 65536, 65537, 1048576]


def run(args, *, cwd=None, capture=False, cpu=None, timeout=1800):
    env = os.environ.copy()
    env["CARGO_TARGET_DIR"] = str(cwd / "target") if cwd else str(OUTPUT / "unused-target")
    affinity = (lambda: os.sched_setaffinity(0, {cpu})) if cpu is not None else None
    return subprocess.run(args, cwd=cwd, env=env, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None,
                          preexec_fn=affinity, timeout=timeout)


def git(checkout, *args):
    return run(["git", *args], cwd=checkout, capture=True).stdout.strip()


def pattern(size):
    return bytes(((i * 73) ^ (i >> 3) ^ (i >> 11)) & 255 for i in range(size))


def prepare():
    OUTPUT.mkdir(exist_ok=True)
    assert git(BASELINE, "rev-parse", "HEAD") == BASE_SHA
    assert git(CANDIDATE, "rev-parse", "HEAD") == FIX_SHA
    assert (BASELINE / "Cargo.lock").read_bytes() == (CANDIDATE / "Cargo.lock").read_bytes()
    assert (BASELINE / "Cargo.toml").read_bytes() == (CANDIDATE / "Cargo.toml").read_bytes()
    assert (BASELINE / "crates/formats/Cargo.toml").read_bytes() == (CANDIDATE / "crates/formats/Cargo.toml").read_bytes()
    probe = (VALIDATION / ".github/validation/zip_crc_probe.rs").read_bytes()
    for checkout in (BASELINE, CANDIDATE):
        target = checkout / "crates/formats/examples/zip_crc_probe.rs"
        target.parent.mkdir(exist_ok=True)
        assert not target.exists()
        target.write_bytes(probe)
    new_test = Path("crates/formats/tests/zip_crc32.rs")
    assert not (BASELINE / new_test).exists()
    (BASELINE / new_test).write_bytes((CANDIDATE / new_test).read_bytes())
    for label, checkout in (("baseline", BASELINE), ("candidate", CANDIDATE)):
        print("BUILD_RELEASE", label, git(checkout, "rev-parse", "HEAD"), flush=True)
        # The new compatibility assertions must pass both versions.
        run(["cargo", "test", "--release", "--locked", "-p", "craft-anything-formats",
             "--test", "zip_crc32"], cwd=checkout)
        run(["cargo", "build", "--release", "--locked", "-p", "craft-anything-formats",
             "--example", "zip_crc_probe"], cwd=checkout)
        run(["git", "diff", "--exit-code"], cwd=checkout)
    print("RELEASE_PROFILES_IDENTICAL", json.dumps({
        "lto": "thin", "codegen_units": 1, "default_opt_level": 3,
        "rustflags": os.environ.get("RUSTFLAGS", ""),
        "cargo_encoded_rustflags": os.environ.get("CARGO_ENCODED_RUSTFLAGS", ""),
        "probe_sha256": hashlib.sha256(probe).hexdigest(),
        "lock_sha256": hashlib.sha256((CANDIDATE / "Cargo.lock").read_bytes()).hexdigest(),
    }), flush=True)


def executable(checkout):
    return str(checkout / "target/release/examples/zip_crc_probe")


def oracle():
    payload = pattern(max(LENGTHS) + 16)
    test = (CANDIDATE / "crates/formats/tests/zip_crc32.rs").read_text()
    constants = re.findall(r"\(([\d_]+), (0x[0-9a-f_]+)\)", test)
    assert len(constants) == len(LENGTHS), (len(constants), len(LENGTHS))
    for length, expected in constants:
        length = int(length.replace("_", ""))
        expected = int(expected.replace("_", ""), 16)
        assert zlib.crc32(payload[:length]) == expected, (length, expected)
    corpus = bytearray(payload)
    cases = [{"offset": offset, "len": length} for length in LENGTHS for offset in range(16)]
    all_bytes_start = len(corpus)
    corpus.extend(range(256))
    cases.extend({"offset": all_bytes_start + value, "len": 1} for value in range(256))
    for value in (0, 255):
        start = len(corpus)
        corpus.extend(bytes([value]) * 65536)
        cases.extend({"offset": start, "len": length} for length in (1, 7, 4096, 65536))
    for public in (b"", b"123456789", b"The quick brown fox jumps over the lazy dog", bytes(range(256))):
        start = len(corpus)
        corpus.extend(public)
        cases.append({"offset": start, "len": len(public)})
    expected = [zlib.crc32(corpus[c["offset"]:c["offset"] + c["len"]]) for c in cases]
    corpus_path = OUTPUT / "crc-corpus.bin"
    cases_path = OUTPUT / "crc-cases.json"
    corpus_path.write_bytes(corpus)
    cases_path.write_text(json.dumps(cases))
    for label, checkout in (("baseline", BASELINE), ("candidate", CANDIDATE)):
        actual = json.loads(run([executable(checkout), "crc", str(corpus_path), str(cases_path)],
                                cwd=checkout, capture=True).stdout)
        assert actual == expected, label
        print("CRC_ORACLE", json.dumps({
            "revision": label, "cases": len(cases), "golden_constants": len(constants),
            "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
            "actual_outputs_sha256": hashlib.sha256(json.dumps(actual).encode()).hexdigest(),
        }), flush=True)
    return {"cases": len(cases), "golden_constants": len(constants), "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION}


def benchmark():
    cpu = min(os.sched_getaffinity(0))
    environment = {
        "platform": platform.platform(), "python": platform.python_version(), "pinned_cpu": cpu,
        "rustc": run(["rustc", "-vV"], cwd=CANDIDATE, capture=True).stdout,
        "base": BASE_SHA, "candidate": FIX_SHA,
        "benchmark": "zip::read_entry: allocation, stored-member copy and CRC validation",
        "outside_timing": "file I/O, central-directory parse, warm-up, equality checks, hashing and deallocation",
        "processes_per_revision_per_size": 5, "bytes_per_process": 128 * 1024 * 1024,
    }
    cpuinfo = Path("/proc/cpuinfo").read_text()
    model = re.search(r"^model name\s*:\s*(.+)$", cpuinfo, re.MULTILINE)
    environment["cpu_model"] = model.group(1) if model else "unreported"
    print("BENCHMARK_ENVIRONMENT", json.dumps(environment), flush=True)
    results = []
    for size in (64 * 1024, 1024 * 1024, 32 * 1024 * 1024):
        payload = pattern(size)
        payload_path = OUTPUT / f"payload-{size}.bin"
        archive_path = OUTPUT / f"stored-{size}.zip"
        payload_path.write_bytes(payload)
        info = zipfile.ZipInfo("payload.bin", date_time=(2020, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_STORED
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr(info, payload)
        with zipfile.ZipFile(archive_path) as archive:
            assert archive.testzip() is None
            assert archive.read("payload.bin") == payload
        identity = {
            "bytes": size, "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "archive_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
            "crc32": zlib.crc32(payload),
        }
        print("FIXTURE_IDENTITY", json.dumps(identity), flush=True)
        iterations = environment["bytes_per_process"] // size
        readings = {"baseline": [], "candidate": []}
        for trial in range(5):
            order = (("baseline", BASELINE), ("candidate", CANDIDATE))
            if trial % 2:
                order = tuple(reversed(order))
            for label, checkout in order:
                reading = json.loads(run([executable(checkout), "zip", str(archive_path), str(payload_path),
                                          str(iterations)], cwd=checkout, capture=True, cpu=cpu, timeout=180).stdout)
                assert reading["bytes"] == size
                assert reading["iterations"] == iterations
                assert reading["crc32"] == identity["crc32"]
                assert reading["output_sha256"] == identity["payload_sha256"]
                assert reading["all_outputs_equal"] is True
                reading["revision"] = label
                reading["trial"] = trial + 1
                reading["mib_per_second"] = size * iterations / (1024 * 1024) / (reading["elapsed_ns"] / 1e9)
                readings[label].append(reading)
                print("STORED_ZIP_READ", json.dumps(reading), flush=True)
        medians = {name: statistics.median(item["mib_per_second"] for item in group)
                   for name, group in readings.items()}
        summary = {**identity, "readings": readings, "median_mib_per_second": medians,
                   "speedup": medians["candidate"] / medians["baseline"]}
        results.append(summary)
        print("STORED_ZIP_SUMMARY", json.dumps({key: value for key, value in summary.items() if key != "readings"}), flush=True)
    report = {"environment": environment, "oracle": oracle_result, "results": results}
    (OUTPUT / "zip-crc-results.json").write_text(json.dumps(report, indent=2) + "\n")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as summary:
            summary.write("## Stored ZIP reads, five fresh processes per version and size\n\n")
            summary.write("| Member size | Baseline MiB/s | Lookup MiB/s | Speedup |\n|---|---:|---:|---:|\n")
            for result in results:
                medians = result["median_mib_per_second"]
                summary.write(f"| {result['bytes']} | {medians['baseline']:.2f} | {medians['candidate']:.2f} | {result['speedup']:.2f}x |\n")
            summary.write("\nEvery timed result was compared byte-for-byte with the identical Python-generated stored member; SHA-256 and CRC matched. These are synthetic Ubuntu runner measurements, not a claim about every archive or device.\n")
    for checkout in (BASELINE, CANDIDATE):
        run(["git", "diff", "--exit-code"], cwd=checkout)
    devlog = CANDIDATE / "log/devlog.md"
    devlog.parent.mkdir(exist_ok=True)
    with devlog.open("a") as log:
        log.write(f"2026-11-11 CRC lookup {FIX_SHA}: 4 compatibility tests pass baseline and candidate; "
                  f"{oracle_result['cases']} zlib cases agree; five actual stored-ZIP-read processes per version "
                  "and size verified byte-identical output. Full crate/contracts/Wasm are in the separate formats job.\n")


if __name__ == "__main__":
    prepare()
    oracle_result = oracle()
    benchmark()
