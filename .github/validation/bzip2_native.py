import bz2, hashlib, json, platform, shutil, subprocess
from pathlib import Path
payloads = {
    "empty": b"",
    "ascii": b"First bzip2 member.\n",
    "unicode": "第二个成员 🧪\n".encode(),
    "binary": bytes(range(256)) * 5,
    "multiblock": bytes(range(251)) * 900,
}
streams = {name: bz2.compress(data, compresslevel=1 if name in ("ascii", "multiblock") else 9) for name, data in payloads.items()}
native_bin = shutil.which("bzip2")
assert native_bin, "The independent native bzip2 CLI is required"
cases = []
def case(name, raw, cap=None, expected=None):
    if expected is None:
        native = subprocess.run([native_bin, "-dc"], input=raw, capture_output=True, timeout=10)
        expected = {"kind": "ok", "bytes": list(native.stdout)} if native.returncode == 0 else {"kind": "corrupt"}
    if cap is None:
        cap = 2_000_000
    if expected["kind"] == "ok" and len(expected["bytes"]) > cap:
        expected = {"kind": "too_large"}
    cases.append({"name": name, "input": list(raw), "cap": cap, "expected": expected})
for name, data in payloads.items():
    case(name, streams[name])
a, b, e, large = streams["ascii"], streams["unicode"], streams["empty"], streams["multiblock"]
for name, raw in {
    "two-members": a+b,
    "three-members": a+b+streams["binary"],
    "empty-first": e+a,
    "empty-middle": a+e+b,
    "empty-last": a+e,
    "only-empty-members": e+e+e,
    "multiblock-then-text": large+a,
    "text-then-multiblock": a+large,
}.items():
    case(name, raw)
bad_block = bytearray(b); bad_block[10] ^= 1
bad_trailer = bytearray(b); bad_trailer[-2] ^= 1
bad_a = bytearray(a); bad_a[10] ^= 1
for name, raw in {
    "bad-first-block-crc": bytes(bad_a)+b,
    "bad-later-block-crc": a+bad_block,
    "bad-later-combined-crc": a+bad_trailer,
    "truncated-later-stream": a+b[:-3],
    "truncated-later-header": a+b[:3],
}.items():
    case(name, raw)
for name, raw, cap in [
    ("exact-combined-budget", a+b, len(payloads["ascii"])+len(payloads["unicode"])),
    ("budget-after-first", a+b, len(payloads["ascii"])),
    ("budget-inside-first", a+b, len(payloads["ascii"])-1),
    ("empty-first-zero-budget", e+a, 0),
    ("all-empty-zero-budget", e+e, 0),
    ("single-exact-budget", a, len(payloads["ascii"])),
]:
    case(name, raw, cap)
for name, raw in [
    ("single-trailing-garbage", a+b"trailing firmware bytes"),
    ("concat-trailing-garbage", a+b+b"trailing firmware bytes"),
    ("single-trailing-zeroes", a+bytes(16)),
]:
    case(name, raw)
bad_empty = bytearray(e); bad_empty[-1] ^= 1
case("bad-later-empty-crc", a+bad_empty)
for name, tail in [("one-byte-header",b"B"), ("two-byte-header",b"BZ"), ("invalid-level-zero",b"BZh0"), ("invalid-level-letter",b"BZhA")]:
    case(name, a+tail)
case("empty-input", b"", expected={"kind": "corrupt"})
case("invalid-input", b"not a bzip2 stream", expected={"kind": "corrupt"})
print("BZ2_ENVIRONMENT="+json.dumps({"python": platform.python_version(), "native_cli": shutil.which("bzip2")}))
if shutil.which("bzip2"):
    p=subprocess.run(["bzip2","--version"],capture_output=True,text=True,timeout=5)
    print("BZ2_NATIVE_VERSION="+(p.stdout+p.stderr).splitlines()[0])
print("BZ2_CONSTANTS="+json.dumps([{"name":n,"plain":list(payloads[n]),"frame":list(streams[n])} for n in ["empty","ascii","unicode"]]))
mismatches=[]
for item in cases:
    p=subprocess.run(["base/target/debug/examples/bzip2_probe"],input=json.dumps({"input":item["input"],"cap":item["cap"]}),capture_output=True,text=True,timeout=5)
    if p.returncode:
        actual={"kind":"process_error","status":p.returncode,"stderr":p.stderr[-1000:]}
    else:
        actual=json.loads(p.stdout)
    if actual != item["expected"]:
        mismatches.append({"name":item["name"],"expected":item["expected"]["kind"],"actual":actual.get("kind"),"expected_bytes":len(item["expected"].get("bytes",[])),"actual_bytes":len(actual.get("bytes",[])),"stderr":actual.get("stderr")})
summary={"cases":len(cases),"mismatches":mismatches,"inputs_sha256":hashlib.sha256(json.dumps(cases,sort_keys=True,separators=(",",":")).encode()).hexdigest()}
print("BZ2_BASELINE="+json.dumps(summary))
assert any(x["name"]=="two-members" and x["actual"]=="ok" and x["actual_bytes"]<x["expected_bytes"] for x in mismatches)
assert not any(x["name"] in payloads for x in mismatches), "single-member controls changed"
Path("bzip2-cases.json").write_text(json.dumps(cases))
