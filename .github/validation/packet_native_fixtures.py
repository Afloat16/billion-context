import ipaddress
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

root = Path(os.environ["PACKET_VALIDATION_FIXTURES"])
root.mkdir(parents=True, exist_ok=True)

def run(args, good=True):
    result = subprocess.run(args, text=True, capture_output=True, timeout=180)
    if good and result.returncode != 0:
        raise AssertionError((args[0], result.returncode, result.stderr[-4000:]))
    return result

versions = {}
for name in ("text2pcap", "editcap", "tshark"):
    exe = shutil.which(name)
    assert exe, name
    output = run([exe, "--version"])
    versions[name] = (output.stdout + output.stderr).splitlines()[0]
print(json.dumps({"native_versions": versions}))

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

def generate(name, n):
    dump = root / (name + ".txt")
    with dump.open("w", encoding="ascii") as out:
        for i in range(n):
            out.write("000000 " + packet(i).hex(" ") + "\n\n")
    ng = root / (name + ".pcapng")
    classic = root / (name + ".pcap")
    run(["text2pcap", "-q", "-F", "pcapng", str(dump), str(ng)])
    run(["editcap", "-F", "pcap", str(ng), str(classic)])
    return ng, classic

def oracle(path, count, good=True):
    result = run(["tshark", "-n", "-r", str(path), "-T", "fields",
                  "-e", "frame.number", "-e", "ip.src", "-e", "ip.dst",
                  "-e", "udp.srcport", "-e", "udp.dstport"], good=good)
    rows = [row.split("\t") for row in result.stdout.splitlines() if row]
    assert len(rows) == count, (path.name, len(rows), count, result.stderr)
    if not good:
        assert result.returncode != 0, path.name
    for i, row in enumerate(rows):
        expected = [str(i + 1), str(ipaddress.IPv4Address(0xc6120000 + i * 2)),
                    str(ipaddress.IPv4Address(0xc6120001 + i * 2)), "40000", "40001"]
        assert row == expected, (path.name, i, row, expected)
    print(json.dumps({"native_file": path.name, "packets": len(rows),
                      "endpoints": len({address for row in rows for address in row[1:3]}),
                      "exit": result.returncode, "prefix_validated": True}))
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

for suffix in ("pcapng", "pcap"):
    output = root / ("empty." + suffix)
    run(["editcap", "-F", suffix, "-r", str(small_ng), str(output), "999999"])
    oracle(output, 0)

manifest = {"versions": versions, "tshark": shutil.which("tshark"),
            "small_packets": 2, "inventory_packets": 5001, "inventory_endpoints": 10002}
(root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
