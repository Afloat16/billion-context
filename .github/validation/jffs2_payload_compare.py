import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess

work = Path("jffs2-native").resolve()
work.mkdir()
mkfs = shutil.which("mkfs.jffs2")
assert mkfs, "mkfs.jffs2 must be installed"
version = subprocess.run([mkfs, "-V"], check=True, capture_output=True, text=True)
cpu = min(os.sched_getaffinity(0))
cpu_name = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("model name")), "unknown")
print("ENVIRONMENT=" + json.dumps({"platform": platform.platform(), "cpu": cpu_name, "pinned_cpu": cpu, "producer": (version.stdout + version.stderr).strip()}), flush=True)
binaries = {name: Path(name, "target/release/examples/jffs2_payload_probe").resolve() for name in ("base", "fixed")}
block = bytes((i * 73 + i // 251) % 256 for i in range(65536))

def sha_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()

def make_fixture(name, size, big_endian=False, compressed=False):
    root = work / (name + "-source")
    (root / "config").mkdir(parents=True)
    with (root / "payload.bin").open("wb") as f:
        for _ in range(size // len(block)):
            f.write(block)
    (root / "config/settings").write_bytes("mode=read-only\nlabel=测试\n".encode())
    (root / "link").symlink_to("payload.bin")
    image = work / (name + ".jffs2")
    command = [mkfs, "-r", str(root), "-o", str(image), "-n", "-f", "-b" if big_endian else "-l"]
    command += ["-m", "priority", "-y", "999:zlib", "-t"] if compressed else ["-m", "none"]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    order = "big" if big_endian else "little"
    nodes = 0
    codecs = set()
    with image.open("rb") as f:
        position = 0
        while position + 12 <= image.stat().st_size:
            f.seek(position)
            header = f.read(12)
            magic = int.from_bytes(header[:2], order)
            if magic != 0x1985:
                assert all(b in (0, 255) for b in header[:4]), (name, position, header.hex())
                position += 4
                continue
            length = int.from_bytes(header[4:8], order)
            assert length >= 12 and position + length <= image.stat().st_size
            if int.from_bytes(header[2:4], order) == 0xe002:
                assert length >= 68
                f.seek(position + 56)
                codecs.add(f.read(1)[0])
                nodes += 1
            position += (length + 3) & ~3
    assert nodes > 0
    assert codecs <= {0, 1, 6}, codecs
    if compressed:
        assert 6 in codecs, "native compressed control must actually contain zlib nodes"
    else:
        assert 0 in codecs and 6 not in codecs
    files = {
        "payload.bin": {"size": size, "sha256": sha_file(root / "payload.bin")},
        "config/settings": {"size": (root / "config/settings").stat().st_size, "sha256": sha_file(root / "config/settings")},
    }
    fixture = {"name": name, "source": root, "image": image, "files": files, "size": size, "codecs": sorted(codecs), "nodes": nodes}
    print("FIXTURE=" + json.dumps({"name": name, "source_bytes": size, "image_bytes": image.stat().st_size, "image_sha256": sha_file(image), "byte_order": order, "data_nodes": nodes, "codecs": sorted(codecs), "command": command, "producer_stderr": result.stderr[-1000:]}), flush=True)
    return fixture

fixtures = {
    "raw_le_16m": make_fixture("raw_le_16m", 16 << 20),
    "raw_be_64m": make_fixture("raw_be_64m", 64 << 20, big_endian=True),
    "skipped_le_64m": make_fixture("skipped_le_64m", 64 << 20),
    "zlib_control": make_fixture("zlib_control", 1 << 20, compressed=True),
}

def run(name, fixture, cap, iteration):
    rss_path = work / (fixture["name"] + "-" + name + "-" + str(iteration) + ".rss")
    command = ["/usr/bin/time", "-f", "%M", "-o", str(rss_path), "taskset", "-c", str(cpu), str(binaries[name]), str(fixture["image"]), str(fixture["source"])]
    if cap is not None:
        command.append(str(cap))
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    output = json.loads(result.stdout)
    metadata = output["image"]
    actual = {x["path"]: x for x in metadata["entries"]}
    assert set(actual) == {"config", "config/settings", "link", "payload.bin"}, actual
    assert actual["config"]["kind"] == "dir"
    assert actual["link"]["kind"] == "symlink"
    assert actual["payload.bin"]["size"] == fixture["size"]
    data = {x["path"]: x for x in output["files"]}
    if cap == 0:
        assert not metadata["complete"] and metadata["bytes"] == 0
        assert output["compared_bytes"] == 0
        assert all(x["data_len"] is None for x in data.values())
        assert any("size budget" in s for s in metadata["warnings"])
    else:
        expected_bytes = sum(x["size"] for x in fixture["files"].values())
        assert metadata["complete"], metadata["warnings"]
        assert output["compared_bytes"] == expected_bytes
        assert metadata["bytes"] == expected_bytes + len("payload.bin")
        assert actual["link"]["symlink_target"] == "payload.bin"
        for path, expected in fixture["files"].items():
            assert actual[path]["kind"] == "file"
            assert data[path]["data_len"] == expected["size"]
            assert data[path]["sha256"] == expected["sha256"]
    reading = {
        "workload": fixture["name"], "version": name, "iteration": iteration,
        "elapsed_ms": output.pop("elapsed_ns") / 1_000_000,
        "peak_rss_kib": int(rss_path.read_text().strip()),
        "complete_output_sha256": output["complete_output_sha256"],
        "compared_bytes": output["compared_bytes"],
    }
    return output, reading

original, _ = run("base", fixtures["zlib_control"], None, "control")
changed, _ = run("fixed", fixtures["zlib_control"], None, "control")
assert original == changed
print("NATIVE_ZLIB_CONTROL=" + json.dumps({"matched": True, "complete_output_sha256": original["complete_output_sha256"], "compared_bytes_per_version": original["compared_bytes"]}), flush=True)
records = []
for workload in ["raw_le_16m", "raw_be_64m", "skipped_le_64m"]:
    expected = None
    for iteration in range(3):
        order = ("base", "fixed") if iteration % 2 == 0 else ("fixed", "base")
        for version_name in order:
            output, reading = run(version_name, fixtures[workload], 0 if workload.startswith("skipped") else None, iteration)
            if expected is None:
                expected = output
            assert output == expected, (workload, version_name, iteration)
            records.append(reading)
            print("READING=" + json.dumps(reading), flush=True)
    summary = {"workload": workload}
    for name in ("base", "fixed"):
        selected = [r for r in records if r["workload"] == workload and r["version"] == name]
        summary[name] = {
            "parse_ms_median": statistics.median(r["elapsed_ms"] for r in selected),
            "peak_rss_kib_median": statistics.median(r["peak_rss_kib"] for r in selected),
        }
    summary["time_ratio"] = summary["base"]["parse_ms_median"] / summary["fixed"]["parse_ms_median"]
    print("SUMMARY=" + json.dumps(summary), flush=True)
assert len(records) == 18
print("All 18 measured runs preserve complete metadata and payload hashes; all recovered native file bytes match their original source files.")
