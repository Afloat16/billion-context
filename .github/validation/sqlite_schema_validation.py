import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BASE = "35f11365026263f43884eadc9ec3296b99893ba1"
FIXED = "98561b89f9792c0c7a42d5e27a5d16aa70936b69"
CARGO = ["cargo", "--config", 'profile.dev.package."*".opt-level=0', "test", "--locked"]
PRODUCT = ["crates/formats/src/sqlite.rs", "crates/engine/src/tools/database_tools.rs"]
NATIVE = Path("crates/engine/tests/sqlite_schema_native_validation.rs")
FORMATS = {
    "complete_schema_keeps_objects_and_table_rows": "ok",
    "a_genuinely_empty_schema_is_complete": "ok",
    "null_cyclic_and_missing_schema_children_keep_readable_siblings": "FAILED",
    "a_reused_schema_leaf_is_retained_once_and_marked_incomplete": "FAILED",
    "wrong_kind_and_unreadable_schema_cells_are_disclosed": "FAILED",
    "truncated_schema_pages_do_not_look_like_a_complete_prefix": "FAILED",
    "an_invalid_schema_root_does_not_look_empty_and_complete": "FAILED",
    "a_schema_depth_limit_keeps_the_readable_prefix_but_is_incomplete": "FAILED",
}
ENGINE = {
    "complete_schema_and_table_pages_keep_existing_coverage": "ok",
    "a_missing_schema_leaf_is_partial_without_an_invented_total": "FAILED",
    "readable_table_pages_do_not_complete_an_incomplete_schema": "FAILED",
    "an_unreadable_schema_root_is_partial_even_with_no_objects": "FAILED",
    "an_incomplete_schema_cannot_establish_that_a_table_is_absent": "FAILED",
}
REAL = {f"native_{name}": ("ok" if name in ("complete", "empty", "row_data_corrupt") else "FAILED")
        for name in ("complete", "null_child", "cyclic_child", "reused_child", "truncated_leaf",
                     "bad_cell", "wrong_root", "header_only", "empty", "row_data_corrupt")}
ENV = dict(os.environ)
ENV["CRAFT_SQLITE_SCHEMA_NATIVE_MANIFEST"] = str(Path(os.environ["RUNNER_TEMP"]) / "sqlite-schema-native" / "cases.json")

def run(crate, target, expected, label):
    command = CARGO + ["-p", crate, "--test", target, "--", "--test-threads=1"]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=ENV)
    print(result.stdout, flush=True)
    observed = dict(re.findall(r"^test (\w+) \.\.\. (ok|FAILED)$", result.stdout, re.M))
    assert observed == expected, json.dumps({"label": label, "expected": expected, "observed": observed}, sort_keys=True)
    wanted_code = 101 if "FAILED" in expected.values() else 0
    assert result.returncode == wanted_code, (label, result.returncode, wanted_code)
    print(json.dumps({"label": label, "returncode": result.returncode,
                      "passed": sum(value == "ok" for value in observed.values()),
                      "failed": sum(value == "FAILED" for value in observed.values())}), flush=True)

assert subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() == FIXED
subprocess.run(["git", "diff", "--exit-code"], check=True)
subprocess.run(["git", "fetch", "--no-tags", "--depth=1", "origin", BASE], check=True)
subprocess.run([sys.executable, str(HERE / "sqlite_schema_native.py")], check=True)
saved = {path: Path(path).read_bytes() for path in PRODUCT}
NATIVE.write_bytes((HERE / "sqlite_schema_native.rs").read_bytes())
try:
    try:
        for path in PRODUCT:
            original = subprocess.check_output(["git", "show", f"{BASE}:{path}"])
            Path(path).write_bytes(original)
            actual = subprocess.check_output(["git", "hash-object", path], text=True).strip()
            expected = subprocess.check_output(["git", "rev-parse", f"{BASE}:{path}"], text=True).strip()
            assert actual == expected
            print(json.dumps({"original_source": path, "base": BASE, "blob": actual}), flush=True)
        changed = set(subprocess.check_output(["git", "diff", "--name-only"], text=True).splitlines())
        assert changed <= set(PRODUCT), changed
        run("craft-anything-formats", "sqlite_schema_completeness", FORMATS, "baseline-formats")
        run("craft-anything-engine", "sqlite_schema_completeness", ENGINE, "baseline-engine")
        run("craft-anything-engine", "sqlite_schema_native_validation", REAL, "baseline-native-sqlite")
    finally:
        for path, contents in saved.items():
            Path(path).write_bytes(contents)
    subprocess.run(["git", "diff", "--exit-code"], check=True)
    run("craft-anything-formats", "sqlite_schema_completeness", dict.fromkeys(FORMATS, "ok"), "fixed-formats")
    run("craft-anything-engine", "sqlite_schema_completeness", dict.fromkeys(ENGINE, "ok"), "fixed-engine")
    run("craft-anything-engine", "sqlite_schema_native_validation", dict.fromkeys(REAL, "ok"), "fixed-native-sqlite")
finally:
    NATIVE.unlink(missing_ok=True)
subprocess.run(["git", "diff", "--exit-code"], check=True)
print("SQLite baseline failures, complete controls and fixed native comparisons all matched.", flush=True)
