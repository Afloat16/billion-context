"""Compile original Java, then independently reject targeted attribute damage with the JVM."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

SOURCE = """public class NativeAttrs {
    public static final int VALUE = 7;
    public static int first(int value) {
        try {
            return second(value);
        } catch (IllegalArgumentException failure) {
            return -1;
        }
    }
    public static int second(int value) {
        return value + 1;
    }
}
"""
PROBE = """import java.nio.file.Files;
import java.nio.file.Paths;
public class AttrProbe extends ClassLoader {
    private Class<?> decode(byte[] bytes) {
        return defineClass(null, bytes, 0, bytes.length);
    }
    public static void main(String[] args) throws Exception {
        try {
            Class<?> type = new AttrProbe().decode(Files.readAllBytes(Paths.get(args[0])));
            int methods = type.getDeclaredMethods().length;
            int fields = type.getDeclaredFields().length;
            System.out.println("accepted " + type.getName() + " methods=" + methods + " fields=" + fields);
        } catch (ClassFormatError failure) {
            System.out.println(failure.getClass().getSimpleName() + ": " + failure.getMessage());
            System.exit(2);
        }
    }
}
"""

def u16(data, pos):
    return struct.unpack_from(">H", data, pos)[0]

def u32(data, pos):
    return struct.unpack_from(">I", data, pos)[0]

def attrs(data, pos, strings):
    count_at = pos
    count = u16(data, pos)
    pos += 2
    rows = []
    for _ in range(count):
        start = pos
        name = u16(data, pos)
        length = u32(data, pos + 2)
        pos += 6
        end = pos + length
        assert end <= len(data)
        rows.append(dict(start=start, length_at=start + 2, info=pos, end=end, name=strings[name]))
        pos = end
    return dict(count_at=count_at, count=count, rows=rows, end=pos)

def layout(data):
    assert data[:4] == bytes.fromhex("cafebabe")
    count = u16(data, 8)
    pos, index = 10, 1
    strings = {}
    while index < count:
        tag = data[pos]
        pos += 1
        if tag == 1:
            length = u16(data, pos)
            pos += 2
            strings[index] = data[pos:pos + length].decode("ascii")
            pos += length
        elif tag in (7, 8, 16, 19, 20):
            pos += 2
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
            pos += 4
        elif tag in (5, 6):
            pos += 8
            index += 1
        elif tag == 15:
            pos += 3
        else:
            raise AssertionError(("unexpected constant tag", tag))
        index += 1
    pos += 6
    interfaces = u16(data, pos)
    pos += 2 + interfaces * 2
    members = {}
    for kind in ("fields", "methods"):
        size = u16(data, pos)
        pos += 2
        rows = []
        for _ in range(size):
            name = strings[u16(data, pos + 2)]
            descriptor = strings[u16(data, pos + 4)]
            table = attrs(data, pos + 6, strings)
            rows.append(dict(name=name, descriptor=descriptor, attrs=table))
            pos = table["end"]
        members[kind] = rows
    final = attrs(data, pos, strings)
    assert final["end"] == len(data)
    members.update(strings=strings, attrs=final)
    return members

def changed_length(data, at):
    out = bytearray(data)
    struct.pack_into(">I", out, at, 0xffffffff)
    return bytes(out)

def shortened_code(data, code, end):
    out = bytearray(data[:end] + data[code["end"]:])
    struct.pack_into(">I", out, code["length_at"], end - code["info"])
    return bytes(out)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "NativeAttrs.java").write_text(SOURCE, encoding="utf-8")
    (out / "AttrProbe.java").write_text(PROBE, encoding="utf-8")
    subprocess.run(["java", "-version"], check=True)
    subprocess.run(["javac", "-version"], check=True)
    subprocess.run(["javac", "-g", "--release", "8", "-d", str(out),
                    str(out / "NativeAttrs.java"), str(out / "AttrProbe.java")], check=True)
    data = (out / "NativeAttrs.class").read_bytes()
    parts = layout(data)
    field = next(row for row in parts["fields"] if row["name"] == "VALUE")
    method = next(row for row in parts["methods"] if row["name"] == "first")
    code = next(row for row in method["attrs"]["rows"] if row["name"] == "Code")
    bytecode_start = code["info"] + 8
    bytecode_end = bytecode_start + u32(data, code["info"] + 4)
    exceptions = u16(data, bytecode_end)
    assert exceptions > 0, "native control must contain a real exception table"
    nested_start = bytecode_end + 2 + exceptions * 8
    nested = attrs(data, nested_start, parts["strings"])
    assert nested["end"] == code["end"] and nested["rows"]
    unknown_name = next(index for index, value in parts["strings"].items() if value == "NativeAttrs")
    unknown = bytearray(data)
    struct.pack_into(">H", unknown, parts["attrs"]["count_at"], parts["attrs"]["count"] + 1)
    unknown += struct.pack(">HI", unknown_name, 4) + b"\x00\xff\x80\x01"
    unknown = bytes(unknown)

    cases = [
        ("complete.class", "complete", data, True),
        ("opaque.class", "opaque", unknown, True),
        ("class-count.class", "class_count", data[:parts["attrs"]["count_at"]], False),
        ("class-header.class", "class_header", data[:parts["attrs"]["rows"][0]["start"] + 1], False),
        ("class-payload.class", "class_payload", data[:-1], False),
        ("class-oversized.class", "class_oversized", changed_length(unknown, len(data) + 2), False),
        ("field-count.class", "field_count", data[:field["attrs"]["count_at"]], False),
        ("method-count.class", "method_count", data[:method["attrs"]["count_at"]], False),
        ("code-count.class", "code_count", shortened_code(data, code, nested_start), False),
        ("code-header.class", "code_header", shortened_code(data, code, nested_start + 3), False),
        ("code-payload.class", "code_payload", shortened_code(data, code, nested["rows"][0]["end"] - 1), False),
        ("code-oversized.class", "code_oversized", changed_length(data, nested["rows"][0]["length_at"]), False),
        ("outer-code-oversized.class", "outer_code_oversized", changed_length(data, code["length_at"]), False),
    ]
    records = []
    for name, kind, content, accepted in cases:
        path = out / name
        path.write_bytes(content)
        result = subprocess.run(["java", "-Xverify:all", "-cp", str(out), "AttrProbe", str(path)],
                                text=True, capture_output=True)
        record = dict(file=name, kind=kind, bytes=len(content), sha256=hashlib.sha256(content).hexdigest(),
                      accepted=accepted, returncode=result.returncode, stdout=result.stdout.strip(),
                      stderr=result.stderr.strip())
        print(json.dumps(record, sort_keys=True), flush=True)
        assert result.returncode == (0 if accepted else 2), record
        if accepted:
            assert "accepted NativeAttrs methods=2 fields=1" in result.stdout, record
        else:
            assert "ClassFormatError:" in result.stdout, record
        records.append(record)
    manifest = dict(class_name="NativeAttrs",source_sha256=hashlib.sha256(SOURCE.encode()).hexdigest(),
                    original_sha256=hashlib.sha256(data).hexdigest(), exception_entries=exceptions, cases=records)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("NATIVE_JVM_ATTRIBUTE_COMPARISON " + json.dumps(dict(files=len(records), accepted=2, rejected=11), sort_keys=True))

if __name__ == "__main__":
    main()
