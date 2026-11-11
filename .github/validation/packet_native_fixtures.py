import ipaddress
import json
import os
from pathlib import Path
import struct
import subprocess

root = Path(os.environ["PACKET_VALIDATION_FIXTURES"])
root.mkdir(parents=True, exist_ok=True)

def run(args, good=True):
    result = subprocess.run(args, text=True, capture_output=True, timeout=180)
    if good and result.returncode != 0:
        raise AssertionError((args[0], result.returncode, result.stderr[-4000:]))
    return result

helper = os.environ["PACKET_NATIVE_HELPER"]
version = run([helper, "--version"]).stdout.strip()
print(json.dumps({"native_version": version, "source_sha": "bbcbc9174df3298a854daee2b3e666a4b6e5383a"}))

def packet(i):
    src = ipaddress.IPv4Address(0xc6120000 + i * 2).packed
    dst = ipaddress.IPv4Address(0xc6120001 + i * 2).packed
    data = b"capture-evidence-" + struct.pack(">I", i)
    udp = struct.pack(">HHHH", 40000, 40001, 8 + len(data), 0) + data
    ip = bytearray(struct.pack(">BBHHHBBH4s4s", 0x45, 0, 20 + len(udp), i & 65535, 0, 64, 17, 0, src, dst))
    checksum = sum(struct.unpack(">10H", ip))
    while checksum >> 16:
        checksum = (checksum & 65535) + (checksum >> 16)
    struct.pack_into(">H", ip, 10, (~checksum) & 65535)
    return bytes.fromhex("aabbccddeeff0200000000010800") + ip + udp

def block(kind, body):
    body += bytes((-len(body)) % 4)
    length = len(body) + 12
    return struct.pack("<II", kind, length) + body + struct.pack("<I", length)

def generate(name, n):
    frames = root / (name + ".frames")
    with frames.open("wb") as out:
        for i in range(n):
            frame = packet(i)
            out.write(struct.pack("<I", len(frame)) + frame)
    classic = root / (name + ".pcap")
    run([helper, "write", str(frames), str(classic)])
    # libpcap writes classic captures. Independently encode the standard pcapng
    # container, then require libpcap to read every packet and timestamp back.
    ng = root / (name + ".pcapng")
    with ng.open("wb") as out:
        out.write(block(0x0a0d0d0a, struct.pack("<IHHq", 0x1a2b3c4d, 1, 0, -1)))
        out.write(block(1, struct.pack("<HHI", 1, 0, 65535)))
        for i in range(n):
            frame = packet(i)
            timestamp = (1700000000 + i) * 1000000 + 500
            body = struct.pack("<IIIII", 0, timestamp >> 32, timestamp & 0xffffffff, len(frame), len(frame)) + frame
            out.write(block(6, body))
    return ng, classic

def oracle(path, count, good=True):
    result = run([helper, "read", str(path)], good=good)
    rows = [row.split("\t") for row in result.stdout.splitlines() if row]
    assert len(rows) == count, (path.name, len(rows), count, result.stderr)
    if not good:
        assert result.returncode == 2, path.name
    for i, row in enumerate(rows):
        frame = packet(i)
        expected = [str(i + 1), str(len(frame)), str(len(frame)), str(1700000000 + i),
                    "500", "1", frame.hex()]
        assert row == expected, (path.name, i, row, expected)
    print(json.dumps({"native_file": path.name, "packets": len(rows),
                      "endpoints": count * 2, "exit": result.returncode,
                      "payloads_lengths_timestamps_link_type_validated": True}))
    return rows

small_ng, small_pcap = generate("small", 2)
large_ng, large_pcap = generate("inventory", 5001)
for path, count in ((small_ng, 2), (small_pcap, 2), (large_ng, 5001), (large_pcap, 5001)):
    oracle(path, count)

classic = small_pcap.read_bytes()
endian = "<" if classic[:4] in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1") else ">"
first_length = struct.unpack_from(endian + "I", classic, 32)[0]
second = 24 + 16 + first_length
cut_classic = root / "damaged.pcap"
cut_classic.write_bytes(classic[:second + 16 + 10])
oracle(cut_classic, 1, good=False)

ng = small_ng.read_bytes()
offset, epbs = 0, []
while offset < len(ng):
    kind, length = struct.unpack_from("<II", ng, offset)
    assert length >= 12 and offset + length <= len(ng)
    if kind == 6:
        epbs.append(offset)
    offset += length
assert len(epbs) == 2
cut_ng = root / "damaged.pcapng"
cut_ng.write_bytes(ng[:epbs[-1] + 8 + 20 + 10])
oracle(cut_ng, 1, good=False)

empty_ng, empty_pcap = generate("empty", 0)
oracle(empty_ng, 0)
oracle(empty_pcap, 0)
manifest = {"native_version": version, "source_sha": "bbcbc9174df3298a854daee2b3e666a4b6e5383a",
            "small_packets": 2, "inventory_packets": 5001, "inventory_endpoints": 10002,
            "scope": "Classic written and read by libpcap; generated pcapng checked by libpcap. No live traffic or real tshark run."}
(root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
