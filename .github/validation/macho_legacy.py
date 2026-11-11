import json
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile

BASE = "2cee4610f07164920ca9f02cd75cd84fa99cba3b"
CARGO = ["cargo", "--config", 'profile.dev.package."*".opt-level=0']
TARGETS = [
    ("macos", "x86_64-apple-macos10.12.1", 0x24),
    ("ios", "arm64-apple-ios9.3.2", 0x25),
    ("tvos", "arm64-apple-tvos9.1.2", 0x2F),
    ("watchos", "armv7k-apple-watchos2.0.1", 0x30),
]


def baseline():
    source = pathlib.Path("crates/formats/src/macho.rs")
    fixed = source.read_bytes()
    try:
        source.write_bytes(subprocess.check_output(["git", "show", BASE + ":crates/formats/src/macho.rs"]))
        result = subprocess.run(
            CARGO + ["test", "--locked", "-p", "craft-anything-formats", "--test", "macho_legacy_versions", "--", "--test-threads=1"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        print(result.stdout, flush=True)
        expected = [
            "legacy_macos_and_ios_keep_their_sdk_in_the_binary_view",
            "legacy_tv_and_watch_versions_reach_the_binary_view",
            "legacy_command_labels_agree_in_both_views",
        ]
        if result.returncode == 0 or "test result: FAILED. 4 passed; 3 failed;" not in result.stdout:
            raise SystemExit("Expected exactly three semantic failures and four passing controls")
        for name in expected:
            if "test " + name + " ... FAILED" not in result.stdout:
                raise SystemExit("Missing semantic failure: " + name)
    finally:
        source.write_bytes(fixed)


def version(value):
    return f"{value >> 16}.{(value >> 8) & 255}.{value & 255}"


def legacy_record(data, command):
    magic, = struct.unpack_from("<I", data)
    if magic not in (0xFEEDFACE, 0xFEEDFACF):
        return None
    pos = 32 if magic == 0xFEEDFACF else 28
    count, size = struct.unpack_from("<II", data, 16)
    limit = pos + size
    for _ in range(count):
        cmd, length = struct.unpack_from("<II", data, pos)
        if length < 8 or pos + length > limit:
            raise ValueError("Compiler output has an invalid load command extent")
        if cmd == command:
            if length < 16:
                raise ValueError("Compiler output has an incomplete version command")
            minimum, sdk = struct.unpack_from("<II", data, pos + 8)
            return version(minimum), version(sdk)
        pos += length
    return None


def clang_objects():
    compiler = shutil.which("clang")
    if compiler is None:
        print("CLANG_FIXTURES_SKIPPED: clang is unavailable", flush=True)
        return
    subprocess.run([compiler, "--version"], check=True)
    probe = pathlib.Path("crates/formats/tests/macho_legacy_clang_probe.rs")
    if probe.exists():
        raise SystemExit("Refusing to overwrite an existing integration test")
    with tempfile.TemporaryDirectory(prefix="craft-macho-") as folder:
        root = pathlib.Path(folder)
        source = root / "sample.c"
        source.write_text("int craft_macho_sample(void) { return 7; }\n", encoding="utf-8")
        cases = []
        for platform, target, command in TARGETS:
            output = root / (platform + ".o")
            result = subprocess.run(
                [compiler, "--target=" + target, "-ffreestanding", "-c", str(source), "-o", str(output)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            if result.returncode:
                print(f"CLANG_TARGET_SKIPPED {target}: {result.stdout.strip()}", flush=True)
                continue
            record = legacy_record(output.read_bytes(), command)
            if record is None:
                print(f"CLANG_TARGET_SKIPPED {target}: compiler did not emit the legacy command", flush=True)
                continue
            minimum, sdk = record
            print(f"CLANG_OBJECT {platform} target={target} command={command:#x} minimum={minimum} sdk={sdk} bytes={output.stat().st_size}", flush=True)
            cases.append((output.name, platform, minimum, sdk))
        if not cases:
            print("CLANG_FIXTURES_SKIPPED: no legacy commands were produced", flush=True)
            return
        rows = ",\n".join("(" + ", ".join(json.dumps(value) for value in case) + ")" for case in cases)
        rust = (
            "use craft_anything_formats::{macho_deps, parse_binary};\n"
            "#[test]\n"
            "fn compiled_legacy_objects_agree_in_both_views() {\n"
            'let folder = std::env::var("CRAFT_MACHO_FIXTURE_DIR").unwrap();\n'
            "for (file, platform, minimum, sdk) in [\n" + rows + "\n] {\n"
            "let data = std::fs::read(std::path::Path::new(&folder).join(file)).unwrap();\n"
            "let binary = parse_binary(&data).unwrap();\n"
            "let deps = macho_deps::parse_thin(&data).unwrap();\n"
            'assert_eq!(binary.info.get("platform").map(String::as_str), Some(platform));\n'
            'assert_eq!(binary.info.get("min_os").map(String::as_str), Some(minimum));\n'
            'assert_eq!(binary.info.get("sdk").map(String::as_str), Some(sdk));\n'
            "assert_eq!(deps.build_versions.len(), 1);\n"
            "assert_eq!(deps.build_versions[0].platform, platform);\n"
            "assert_eq!(deps.build_versions[0].minos, minimum);\n"
            "assert_eq!(deps.build_versions[0].sdk.as_deref(), Some(sdk));\n"
            'println!("CLANG_PARSED {file}: {platform} {minimum} SDK {sdk}");\n'
            "}\n}\n"
        )
        try:
            probe.write_text(rust, encoding="utf-8")
            result = subprocess.run(
                CARGO + ["test", "--locked", "-p", "craft-anything-formats", "--test", "macho_legacy_clang_probe", "--", "--nocapture"],
                env={**os.environ, "CRAFT_MACHO_FIXTURE_DIR": folder},
            )
            if result.returncode:
                raise SystemExit(result.returncode)
        finally:
            probe.unlink(missing_ok=True)


if __name__ == "__main__":
    if sys.argv[1] == "baseline":
        baseline()
    elif sys.argv[1] == "clang":
        clang_objects()
    else:
        raise SystemExit("Expected baseline or clang")
