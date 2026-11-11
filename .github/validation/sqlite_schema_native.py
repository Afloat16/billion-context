import hashlib
import json
import os
from pathlib import Path
import sqlite3

ROOT = Path(os.environ["RUNNER_TEMP"]) / "sqlite-schema-native"
ROOT.mkdir(exist_ok=True)
DB = ROOT / "complete.db"
with sqlite3.connect(DB) as connection:
    connection.execute("PRAGMA page_size=512")
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("VACUUM")
    connection.execute("CREATE TABLE items(id INTEGER PRIMARY KEY, value TEXT)")
    connection.executemany("INSERT INTO items(value) VALUES (?)", [(f"value-{i}",) for i in range(10)])
    connection.execute("CREATE INDEX items_value ON items(value)")
    connection.execute("CREATE TRIGGER items_insert AFTER INSERT ON items BEGIN SELECT NEW.value; END")
    for i in range(160):
        connection.execute(f"CREATE VIEW view_{i:04d} AS SELECT id, value FROM items")
    connection.commit()
    assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    schema = [
        {"rowid": row[0], "type": row[1], "name": row[2], "tbl_name": row[3], "rootpage": row[4], "sql": row[5]}
        for row in connection.execute("SELECT rowid,type,name,tbl_name,rootpage,sql FROM sqlite_schema ORDER BY rowid")
    ]
    table_rows = [{"rowid": row[0], "values": list(row)} for row in connection.execute("SELECT id,value FROM items ORDER BY id")]
data = DB.read_bytes()
PAGE = int.from_bytes(data[16:18], "big")
assert PAGE == 512 and data[100] == 5

def u16(offset):
    return int.from_bytes(data[offset:offset + 2], "big")

def u32(offset):
    return int.from_bytes(data[offset:offset + 4], "big")

def varint(offset):
    value = 0
    for n in range(9):
        byte = data[offset + n]
        value = (value << (8 if n == 8 else 7)) | (byte if n == 8 else byte & 127)
        if n == 8 or byte < 128:
            return value, offset + n + 1
    raise AssertionError("unreachable varint")

leaves = {}
children = {}
def visit(page):
    base = (page - 1) * PAGE
    header = base + (100 if page == 1 else 0)
    count = u16(header + 3)
    kind = data[header]
    if kind == 13:
        rows = []
        for i in range(count):
            cell = base + u16(header + 8 + 2 * i)
            _, after_payload_size = varint(cell)
            rowid, _ = varint(after_payload_size)
            rows.append(rowid)
        leaves[page] = rows
        return rows
    assert kind == 5
    child_pages = [u32(base + u16(header + 12 + 2 * i)) for i in range(count)]
    child_pages.append(u32(header + 8))
    children[page] = child_pages
    return [rowid for child in child_pages for rowid in visit(child)]

assert visit(1) == [row["rowid"] for row in schema]
assert len(leaves) >= 3
def subtree(page):
    if page in leaves:
        return leaves[page]
    return [rowid for child in children[page] for rowid in subtree(child)]

def check_with_sqlite(path):
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchall()
        return "ok" if result == [("ok",)] else repr(result)
    except sqlite3.DatabaseError as error:
        return str(error)

cases = []
def add(name, content, omitted=(), incomplete=False, row_data_intact=True, expected=None):
    path = ROOT / f"{name}.db"
    path.write_bytes(content)
    rows = [row for row in schema if row["rowid"] not in set(omitted)] if expected is None else expected
    expected_schema = [{key: value for key, value in row.items() if key != "rowid"} for row in rows]
    oracle = check_with_sqlite(path)
    if incomplete:
        assert oracle != "ok", (name, oracle)
    elif row_data_intact:
        assert oracle == "ok", (name, oracle)
    cases.append({
        "name": name,
        "file": str(path.resolve()),
        "schema": expected_schema,
        "incomplete": incomplete,
        "check_rows": row_data_intact and any(row["name"] == "items" for row in rows),
        "rows": table_rows,
    })
    print(json.dumps({
        "case": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
        "retained_schema_objects": len(rows), "schema_incomplete": incomplete,
        "sqlite_integrity": oracle,
    }), flush=True)

add("complete", data)
first_pointer = u16(112)
first_child = u32(first_pointer)
right_child = u32(108)
assert first_child != right_child

bad = bytearray(data)
bad[108:112] = bytes(4)
add("null_child", bad, subtree(right_child), True)

bad = bytearray(data)
bad[first_pointer:first_pointer + 4] = (1).to_bytes(4, "big")
add("cyclic_child", bad, subtree(first_child), True)

bad = bytearray(data)
bad[108:112] = first_child.to_bytes(4, "big")
add("reused_child", bad, subtree(right_child), True)

last_leaf = max(leaves)
cut = (last_leaf - 1) * PAGE
def rows_before_cut(page):
    if (page - 1) * PAGE >= cut:
        return []
    if page in leaves:
        return leaves[page]
    return [rowid for child in children[page] for rowid in rows_before_cut(child)]
retained = set(rows_before_cut(1))
add("truncated_leaf", data[:cut], [row["rowid"] for row in schema if row["rowid"] not in retained], True)

bad = bytearray(data)
bad[cut + 8:cut + 10] = (65535).to_bytes(2, "big")
add("bad_cell", bad, [leaves[last_leaf][0]], True)

bad = bytearray(data)
bad[100] = 10
add("wrong_root", bad, [row["rowid"] for row in schema], True)
add("header_only", data[:100], [row["rowid"] for row in schema], True)

empty_path = ROOT / "empty.db"
with sqlite3.connect(empty_path) as connection:
    connection.execute("PRAGMA page_size=512")
    connection.execute("VACUUM")
    assert connection.execute("SELECT count(*) FROM sqlite_schema").fetchone() == (0,)
add("empty", empty_path.read_bytes(), expected=[])

items_root = next(row["rootpage"] for row in schema if row["name"] == "items")
bad = bytearray(data)
bad[(items_root - 1) * PAGE] = 0
add("row_data_corrupt", bad, row_data_intact=False)

manifest = ROOT / "cases.json"
manifest.write_text(json.dumps(cases, ensure_ascii=False, indent=2))
print(json.dumps({"sqlite_version": sqlite3.sqlite_version, "cases": len(cases), "schema_leaves": len(leaves),
                  "complete_objects": len(schema), "manifest": str(manifest)}), flush=True)
