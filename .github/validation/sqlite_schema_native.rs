use craft_anything_engine::{CallOptions, Caller, Engine, ToolOutput};
use craft_anything_formats::sqlite::SqliteDb;
use serde_json::{Value, json};

fn check(name: &str) {
    let manifest: Value = serde_json::from_slice(&std::fs::read(std::env::var("CRAFT_SQLITE_SCHEMA_NATIVE_MANIFEST").unwrap()).unwrap()).unwrap();
    let case = manifest.as_array().unwrap().iter().find(|case| case["name"] == name).unwrap();
    let path = case["file"].as_str().unwrap();
    let bytes = std::fs::read(path).unwrap();
    let database = SqliteDb::parse(&bytes).unwrap();
    let (objects, incomplete) = database.schema();
    let schema = objects.iter().map(|object| json!({
        "type": object.obj_type, "name": object.name, "tbl_name": object.tbl_name,
        "rootpage": object.rootpage, "sql": object.sql,
    })).collect::<Vec<_>>();
    assert_eq!(json!(schema), case["schema"], "retained native schema objects: {name}");
    assert_eq!(json!(incomplete), case["incomplete"], "schema flag: {name}");
    assert_eq!(json!(database.overview().schema_truncated), case["incomplete"], "overview flag: {name}");

    let engine = Engine::new(craft_anything_engine::testing::session());
    let call = |params| {
        let output = engine.call("db_sqlite_show", params, CallOptions::new(Caller::Mcp)).unwrap();
        let ToolOutput::Evidence(record) = output else { panic!("expected SQLite evidence") };
        assert!(record.verify());
        serde_json::to_value(&*record).unwrap()
    };
    let listing = call(json!({"path": path}));
    let expected_tables = objects.iter().filter(|object| object.obj_type == "table" && object.rootpage != 0).collect::<Vec<_>>();
    assert_eq!(listing["result"]["tables"].as_array().unwrap().len(), expected_tables.len(), "tables: {name}");
    assert_eq!(listing["result"]["other_objects"].as_array().unwrap().len(), objects.len() - expected_tables.len(), "others: {name}");
    assert_eq!(listing["result"]["schema_truncated"], case["incomplete"]);
    assert_eq!(listing["coverage"]["status"], if incomplete { "partial" } else { "complete" }, "tool coverage: {name}");
    assert_eq!(listing["coverage"]["examined"], json!(expected_tables.len()));
    assert_eq!(listing["coverage"]["total"], if incomplete { Value::Null } else { json!(expected_tables.len()) });
    assert_eq!(
        listing["limitations"].as_array().unwrap().iter().any(|limitation| limitation["code"] == "schema_incomplete"),
        incomplete,
    );
    if case["check_rows"] == true {
        let rows = call(json!({"path": path, "table": "items", "limit": 100}));
        assert_eq!(rows["result"]["rows"]["rows"], case["rows"], "native table rows: {name}");
        assert_eq!(rows["coverage"]["status"], if incomplete { "partial" } else { "complete" });
        assert_eq!(rows["coverage"]["total"], case["rows"].as_array().unwrap().len());
        assert!(rows["coverage"]["next_offset"].is_null());
        assert_eq!(rows["result"]["rows"]["truncated"], false);
    }
}

#[test] fn native_complete() { check("complete"); }
#[test] fn native_null_child() { check("null_child"); }
#[test] fn native_cyclic_child() { check("cyclic_child"); }
#[test] fn native_reused_child() { check("reused_child"); }
#[test] fn native_truncated_leaf() { check("truncated_leaf"); }
#[test] fn native_bad_cell() { check("bad_cell"); }
#[test] fn native_wrong_root() { check("wrong_root"); }
#[test] fn native_header_only() { check("header_only"); }
#[test] fn native_empty() { check("empty"); }
#[test] fn native_row_data_corrupt() { check("row_data_corrupt"); }
