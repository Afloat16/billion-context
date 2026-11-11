use craft_anything_engine::{CallOptions, Caller, Engine, ToolOutput};
use craft_anything_formats::java_class::{self, ClassFile};
use serde_json::{Value, json};
use std::path::PathBuf;

fn path(name: &str) -> PathBuf {
    PathBuf::from(std::env::var("JAVA_ATTRIBUTE_FIXTURES").unwrap()).join(name)
}

fn parse(name: &str) -> ClassFile {
    let class = java_class::parse(&std::fs::read(path(name)).unwrap()).unwrap();
    assert_eq!(class.this_class, "NativeAttrs");
    assert_eq!(class.super_class.as_deref(), Some("java/lang/Object"));
    class
}

fn call(name: &str, tool: &str, mut params: Value) -> Value {
    let engine = Engine::new(craft_anything_engine::testing::session());
    params["path"] = json!(path(name));
    match engine.call(tool, params, CallOptions::new(Caller::Cli)).unwrap() {
        ToolOutput::Evidence(value) => {
            assert!(value.verify());
            serde_json::to_value(value).unwrap()
        }
        other => panic!("expected Java evidence, got {other:?}"),
    }
}

fn partial(name: &str) {
    let value = call(name, "java_class_show", json!({"decompile": false}));
    assert_eq!(value["result"]["name"], "NativeAttrs");
    assert_eq!(value["coverage"]["status"], "partial");
    assert!(value["coverage"]["total"].is_null());
    assert!(value["limitations"].as_array().unwrap().iter().any(|item| item["code"] == "parse_warning"));
}

fn readable_methods(name: &str, source_file: bool) {
    let complete = parse("complete.class");
    let class = parse(name);
    assert!(!class.warnings.is_empty());
    assert_eq!(class.fields, complete.fields);
    assert_eq!(class.methods, complete.methods);
    if source_file {
        assert_eq!(class.source_file, complete.source_file);
    }
    partial(name);
    let references = call(name, "java_class_users_find", json!({"class_name": "NativeAttrs", "method_name": "second"}));
    assert_eq!(references["coverage"]["status"], "partial");
    assert_eq!(references["result"]["references_total"], 1);
}

#[test]
fn native_javac_control_preserves_exceptions_and_calls() {
    let class = parse("complete.class");
    assert!(class.warnings.is_empty());
    assert_eq!(class.source_file.as_deref(), Some("NativeAttrs.java"));
    assert_eq!(class.fields[0].constant_value.as_deref(), Some("7"));
    assert_eq!(class.methods.len(), 3);
    let first = class.methods.iter().find(|method| method.name == "first").unwrap().code.as_ref().unwrap();
    assert!(!first.bytecode.is_empty());
    assert!(!first.exceptions.is_empty());
    assert!(!first.line_numbers.is_empty());
    let value = call("complete.class", "java_class_users_find", json!({"class_name": "NativeAttrs", "method_name": "second"}));
    assert_eq!(value["coverage"]["status"], "complete");
    assert_eq!(value["result"]["references_total"], 1);
}

#[test]
fn native_jvm_accepted_opaque_attribute_is_still_ignored() {
    let class = parse("opaque.class");
    let original = parse("complete.class");
    assert!(class.warnings.is_empty());
    assert_eq!(class.fields, original.fields);
    assert_eq!(class.methods, original.methods);
    assert_eq!(class.source_file, original.source_file);
    let value = call("opaque.class", "java_class_show", json!({"decompile": false}));
    assert_eq!(value["coverage"]["status"], "complete");
}

#[test]
fn native_missing_class_attribute_count_preserves_readable_class_facts() {
    readable_methods("class-count.class", false);
}

#[test]
fn native_truncated_class_attribute_headers_and_payloads_preserve_members() {
    for name in ["class-header.class", "class-payload.class"] {
        readable_methods(name, false);
    }
}

#[test]
fn native_oversized_class_attribute_preserves_the_preceding_source_name() {
    readable_methods("class-oversized.class", true);
}

#[test]
fn native_missing_field_attribute_count_preserves_its_header_and_marks_unknown_methods() {
    let class = parse("field-count.class");
    assert!(!class.warnings.is_empty());
    assert_eq!(class.fields.len(), 1);
    assert_eq!(class.fields[0].name, "VALUE");
    assert_eq!(class.fields[0].descriptor, "I");
    assert!(class.methods.is_empty());
    partial("field-count.class");
    let engine = Engine::new(craft_anything_engine::testing::session());
    let error = engine
        .call("java_method_show", json!({"path": path("field-count.class"), "method_name": "first"}), CallOptions::new(Caller::Cli))
        .unwrap_err();
    let error = serde_json::to_value(error).unwrap();
    assert_eq!(error["details"]["parse_incomplete"], true);
    assert!(error["message"].as_str().unwrap().contains("readable"));
}

#[test]
fn native_missing_method_attribute_count_keeps_the_constructor_and_member_identity() {
    let class = parse("method-count.class");
    assert!(!class.warnings.is_empty());
    assert_eq!(class.fields[0].constant_value.as_deref(), Some("7"));
    assert_eq!(class.methods.len(), 2);
    assert_eq!(class.methods[0].name, "<init>");
    assert!(class.methods[0].code.is_some());
    assert_eq!(class.methods[1].name, "first");
    assert!(class.methods[1].code.is_none());
    partial("method-count.class");
}

#[test]
fn native_damaged_nested_attributes_keep_real_bytecode_exceptions_and_later_methods() {
    let original = parse("complete.class");
    let first = original.methods.iter().find(|method| method.name == "first").unwrap().code.as_ref().unwrap();
    let second = original.methods.iter().find(|method| method.name == "second").unwrap();
    for name in ["code-count.class", "code-header.class", "code-payload.class", "code-oversized.class"] {
        let class = parse(name);
        assert!(!class.warnings.is_empty(), "{name}");
        assert_eq!(class.methods.len(), 3, "{name}");
        let parsed = class.methods.iter().find(|method| method.name == "first").unwrap().code.as_ref().unwrap();
        assert_eq!(parsed.bytecode, first.bytecode, "{name}");
        assert_eq!(parsed.exceptions, first.exceptions, "{name}");
        assert_eq!(class.methods.iter().find(|method| method.name == "second").unwrap(), second);
        assert_eq!(class.source_file, original.source_file);
        partial(name);
        let method = call(name, "java_method_show", json!({"method_name": "first", "decompile": false}));
        assert_eq!(method["coverage"]["status"], "partial");
        assert!(method["result"]["instructions_total"].as_u64().unwrap() > 0);
        let references = call(name, "java_class_users_find", json!({"class_name": "NativeAttrs", "method_name": "second"}));
        assert_eq!(references["coverage"]["status"], "partial");
        assert_eq!(references["result"]["references_total"], 1);
    }
}

#[test]
fn native_oversized_outer_code_length_does_not_invent_a_following_method() {
    let class = parse("outer-code-oversized.class");
    assert!(!class.warnings.is_empty());
    assert_eq!(class.fields[0].constant_value.as_deref(), Some("7"));
    assert_eq!(class.methods.len(), 2);
    assert_eq!(class.methods[0].name, "<init>");
    assert!(class.methods[0].code.is_some());
    assert_eq!(class.methods[1].name, "first");
    assert!(class.methods[1].code.is_none());
    partial("outer-code-oversized.class");
    let method = call("outer-code-oversized.class", "java_method_show", json!({"method_name": "first", "decompile": false}));
    assert_eq!(method["coverage"]["status"], "partial");
    assert!(method["limitations"].as_array().unwrap().iter().any(|item| {
        item["code"] == "no_code" && item["message"].as_str().unwrap_or_default().contains("readable")
    }));
}
