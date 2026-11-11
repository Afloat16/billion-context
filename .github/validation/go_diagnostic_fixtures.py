"""Build an original Go executable and add a bounded diagnostic stress region."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

CONTROL = """package main
import "fmt"
var marker = "default"
//go:noinline
func retained(value int) int { return value*3 + 1 }
func main() { fmt.Println(retained(13), marker) }
"""
ORACLE = """package main
import ("debug/buildinfo"; "encoding/json"; "fmt"; "os")
func main() {
    info, err := buildinfo.ReadFile(os.Args[1])
    if err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
    if err := json.NewEncoder(os.Stdout).Encode(info); err != nil { panic(err) }
}
"""

def u16(data, at):
    return struct.unpack_from("<H", data, at)[0]

def u32(data, at):
    return struct.unpack_from("<I", data, at)[0]

def u64(data, at):
    return struct.unpack_from("<Q", data, at)[0]

def align(value, alignment=4096):
    return (value + alignment - 1) // alignment * alignment

def sections(data):
    assert data[:7] == b"\x7fELF\x02\x01\x01"
    table, count, stride, names_index = u64(data, 40), u16(data, 60), u16(data, 58), u16(data, 62)
    assert stride == 64
    names_row = table + names_index * stride
    names = data[u64(data, names_row + 24):u64(data, names_row + 24) + u64(data, names_row + 32)]
    rows = {}
    for index in range(count):
        at = table + index * stride
        name_at = u32(data, at)
        end = names.find(b"\0", name_at)
        assert end >= name_at
        name = names[name_at:end].decode("ascii")
        rows[name] = dict(at=at, offset=u64(data, at + 24), size=u64(data, at + 32), address=u64(data, at + 16))
    return rows

def transformed(original, count):
    rows = sections(original)
    info = rows[".go.buildinfo"]
    blob = original[info["offset"]:info["offset"] + info["size"]]
    assert blob.startswith(b"\xff Go buildinf:") and blob[15] & 2
    phoff, phsize, phnum = u64(original, 32), u16(original, 54), u16(original, 56)
    assert phsize == 56
    extra_header = phoff + phsize * phnum
    first_section_data = min(row["offset"] for row in rows.values() if row["size"] and row["offset"] >= extra_header)
    assert extra_header + phsize <= first_section_data
    assert original[extra_header:extra_header + phsize] == bytes(phsize), "do not overwrite existing data"
    loads = [phoff + index * phsize for index in range(phnum) if u32(original, phoff + index * phsize) == 1]
    address = align(max(u64(original, at + 16) + u64(original, at + 40) for at in loads)) + 4096
    broken = b"\xff Go buildinf:" + bytes([8, 0]) + bytes(16)
    assert len(broken) == 32
    payload = broken * count + blob
    offset = align(len(original))
    output = bytearray(original)
    output[info["offset"]:info["offset"] + 14] = bytes(14)
    output.extend(bytes(offset - len(output)))
    output.extend(payload)
    struct.pack_into("<H", output, 56, phnum + 1)
    headers = [bytearray(original[phoff + index * phsize:phoff + (index + 1) * phsize])
               for index in range(phnum)]
    for header in headers:
        if u32(header, 0) == 6:  # PT_PHDR spans the additional load record too.
            struct.pack_into("<Q", header, 32, (phnum + 1) * phsize)
            struct.pack_into("<Q", header, 40, (phnum + 1) * phsize)
    # Keep load records in ascending virtual-address order and before the trailing
    # zero-sized GNU_STACK record; Go 1.24's DataReader examines every program
    # header, including that empty record, before selecting a later load.
    insert_at = max(index for index, header in enumerate(headers) if u32(header, 0) == 1) + 1
    headers.insert(insert_at, struct.pack("<IIQQQQQQ", 1, 6, offset, address, address,
                                         len(payload), len(payload), 4096))
    output[phoff:phoff + (phnum + 1) * phsize] = b"".join(headers)
    struct.pack_into("<Q", output, info["at"] + 16, address)
    struct.pack_into("<Q", output, info["at"] + 24, offset)
    struct.pack_into("<Q", output, info["at"] + 32, len(payload))
    assert output[offset + count * 32:offset + len(payload)] == blob
    return bytes(output), dict(candidate_probes=count, metadata_offset=offset + count * 32,
                               metadata_address=address + count * 32,
                               metadata_sha256=hashlib.sha256(blob).hexdigest(), payload_bytes=len(payload))

def symbols(path, env):
    text = subprocess.check_output(["go", "tool", "nm", str(path)], text=True, env=env)
    wanted = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[2] in ("main.main", "main.retained"):
            wanted[fields[2]] = int(fields[0], 16)
    assert set(wanted) == {"main.main", "main.retained"}, wanted
    return wanted

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out).resolve()
    src = out / "src"
    for part in ("control", "oracle"):
        (src / part).mkdir(parents=True, exist_ok=True)
    (src / "go.mod").write_text("module example.com/diagnostics\n\ngo 1.22\n")
    (src / "control/main.go").write_text(CONTROL)
    (src / "oracle/main.go").write_text(ORACLE)
    env = dict(os.environ, CGO_ENABLED="0", GOOS="linux", GOARCH="amd64", GOTOOLCHAIN="local",
               GOPROXY="off", GOSUMDB="off", GOWORK="off")
    version = subprocess.check_output(["go", "version"], text=True, env=env).strip()
    print(version, flush=True)
    subprocess.run(["go", "build", "-trimpath", "-buildvcs=false", "-ldflags", "-X main.marker=fixture",
                    "-o", str(out / "control"), "./control"], cwd=src, env=env, check=True)
    subprocess.run(["go", "build", "-trimpath", "-buildvcs=false", "-o", str(out / "oracle"), "./oracle"],
                   cwd=src, env=env, check=True)
    native = json.loads(subprocess.check_output([str(out / "oracle"), str(out / "control")], text=True))
    native_symbols = symbols(out / "control", env)
    original = (out / "control").read_bytes()
    records = []
    for name, count in [("relocated-control", 0), ("single-pointer", 1), ("many-pointers", 262144)]:
        data, facts = transformed(original, count)
        path = out / name
        path.write_bytes(data)
        assert symbols(path, env) == native_symbols
        if count == 0:
            assert json.loads(subprocess.check_output([str(out / "oracle"), str(path)], text=True)) == native
        record = dict(file=name, size=len(data), sha256=hashlib.sha256(data).hexdigest(), **facts)
        records.append(record)
        print("GO_DIAGNOSTIC_FIXTURE " + json.dumps(record, sort_keys=True), flush=True)
    manifest = dict(go_version=version, buildinfo=native, symbols=native_symbols, files=records,
                    control_sha256=hashlib.sha256(original).hexdigest())
    (out / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    print("GO_NATIVE_CONTROL " + json.dumps(manifest, sort_keys=True), flush=True)

if __name__ == "__main__":
    main()
