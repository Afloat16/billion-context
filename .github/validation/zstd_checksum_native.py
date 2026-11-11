import hashlib, json, platform, subprocess
from pathlib import Path
from compression import zstd

payloads = [
    ("empty", b""),
    ("ascii", b"Craft checksums.\n"),
    ("unicode", "校验🧪\n".encode()),
    ("repeated", b"native checksummed data\n" * 50),
    ("multiblock", b"native checksummed data\n" * 10000 + bytes(range(256)) * 1024),
]
cases = []
constants = []
def add(name, frame, expected, cap=None):
    if expected is not None:
        assert zstd.decompress(frame) == expected, name
        result = {"name": name, "status": "ok", "bytes": list(expected)}
    else:
        try:
            zstd.decompress(frame)
        except zstd.ZstdError:
            pass
        else:
            raise AssertionError("native accepted corruption: " + name)
        result = {"name": name, "status": "corrupt"}
    cases.append({"name": name, "frame": list(frame), "cap": len(expected) if cap is None and expected is not None else (cap if cap is not None else 1 << 20), "expected": result})
    return frame
frames = {}
for name, plain in payloads:
    frame = zstd.compress(plain, options={zstd.CompressionParameter.checksum_flag: 1})
    assert frame[4] & 4, name
    frames[name] = frame
    free = zstd.compress(plain, options={zstd.CompressionParameter.checksum_flag: 0})
    assert not free[4] & 4, name
    add(name + "-checked", frame, plain)
    add(name + "-unchecked", free, plain)
    if len(plain) <= 1200:
        constants.append({"name": name, "plain": list(plain), "frame": list(frame), "unchecked": list(free)})
    for index in range(4):
        bad = bytearray(frame)
        bad[-4 + index] ^= 0x80
        add(name + "-checksum-byte-" + str(index), bad, None)
    for removed in range(1, 5):
        add(name + "-truncated-" + str(removed), frame[:-removed], None)
    if plain:
        cases.append({"name": name + "-budget", "frame": list(frame), "cap": len(plain)-1, "expected": {"name": name + "-budget", "status": "too_large"}})
ascii_frame = frames["ascii"]
raw_at = ascii_frame.index(b"Craft checksums.\n")
bad_payload = bytearray(ascii_frame)
bad_payload[raw_at] ^= 1
add("raw-payload-mutated", bad_payload, None)
good = frames["ascii"]
bad = bytearray(frames["unicode"])
bad[-1] ^= 1
skip = b"\x50\x2a\x4d\x18\x03\x00\x00\x00xyz"
add("concatenated-valid", good + skip + frames["unicode"], payloads[1][1] + payloads[2][1])
add("bad-first-frame", bytes(bad) + skip + good, None)
add("bad-later-frame", good + skip + bytes(bad), None)
add("bad-empty-frame", good + frames["empty"][:-1] + bytes([frames["empty"][-1] ^ 1]), None)
Path("zstd-checksum-cases.json").write_text(json.dumps(cases))
print("NATIVE_ENVIRONMENT=" + json.dumps({"python": platform.python_version(), "zstd_version": getattr(zstd, "zstd_version", "not exposed")}))
print("NATIVE_CONSTANTS_JSON=" + json.dumps(constants))
print("NATIVE_CASES=" + json.dumps({"count": len(cases), "payload_corruption_offset": raw_at, "input_hashes": {x["name"]: hashlib.sha256(bytes(x["frame"])).hexdigest() for x in cases}}))
