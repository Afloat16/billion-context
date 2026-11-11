use craft_anything_engine::{CallOptions, Caller, Engine};
use serde_json::{Value, json};
use std::path::PathBuf;

fn fixtures() -> PathBuf {
    PathBuf::from(std::env::var_os("PACKET_VALIDATION_FIXTURES").unwrap())
}

fn call(tool: &str, name: &str, external: bool, mut params: Value) -> Value {
    let mut session = craft_anything_engine::testing::session();
    if external {
        let manifest: Value = serde_json::from_slice(&std::fs::read(fixtures().join("manifest.json")).unwrap()).unwrap();
        session.settings.engines.tools.tshark = Some(PathBuf::from(manifest["tshark"].as_str().unwrap()));
    }
    let engine = Engine::new(session);
    params["path"] = json!(fixtures().join(name));
    engine.call(tool, params, CallOptions::new(Caller::Cli)).unwrap().to_json()
}

fn prefix(name: &str) {
    let overview = call("packets_capture_show", name, false, json!({}));
    assert_eq!(overview["result"]["packets"], 1);
    assert_eq!(overview["coverage"]["status"], "partial");
    assert!(overview["coverage"]["total"].is_null());
    let fields = call("packets_fields_show", name, false, json!({}));
    assert_eq!(fields["result"]["total_packets"], 1);
    assert_eq!(fields["result"]["packets"][0]["src"], "198.18.0.0:40000");
    assert_eq!(fields["result"]["packets"][0]["dst"], "198.18.0.1:40001");
    assert_eq!(fields["coverage"]["status"], "partial");
    assert!(fields["coverage"]["total"].is_null());
    let inventory = call("packets_inventory_show", name, false, json!({"engine": "built_in"}));
    assert_eq!(inventory["result"]["packets"], 1);
    assert_eq!(inventory["result"]["counts"]["endpoints"], 2);
    assert_eq!(inventory["coverage"]["status"], "partial");
    assert!(inventory["coverage"]["total"].is_null());
}

#[test]
fn native_damaged_classic_retains_only_the_readable_prefix() {
    prefix("damaged.pcap");
}

#[test]
fn native_damaged_pcapng_retains_only_the_readable_prefix() {
    prefix("damaged.pcapng");
}

#[test]
fn native_complete_captures_keep_counts_and_fields() {
    for name in ["small.pcap", "small.pcapng"] {
        let overview = call("packets_capture_show", name, false, json!({}));
        assert_eq!(overview["result"]["packets"], 2);
        assert_eq!(overview["coverage"], json!({"status": "complete", "examined": 2, "total": 2}));
        let fields = call("packets_fields_show", name, false, json!({}));
        assert_eq!(fields["result"]["packets"][0]["src"], "198.18.0.0:40000");
        assert_eq!(fields["result"]["packets"][1]["src"], "198.18.0.2:40000");
        assert_eq!(fields["coverage"], json!({"status": "complete", "examined": 2, "total": 2}));
        for (external, kind) in [(false, "built_in"), (true, "tshark")] {
            let inventory = call("packets_inventory_show", name, external, json!({"engine": kind}));
            assert_eq!(inventory["result"]["counts"]["endpoints"], 4);
            assert_eq!(inventory["coverage"], json!({"status": "complete", "examined": 2, "total": 2}));
        }
    }
}

#[test]
fn native_inventory_limit_is_partial_in_both_engines() {
    for name in ["inventory.pcap", "inventory.pcapng"] {
        for (external, kind) in [(false, "built_in"), (true, "tshark")] {
            let inventory = call("packets_inventory_show", name, external, json!({"engine": kind, "limit": 10000}));
            assert_eq!(inventory["result"]["packets"], 5001);
            assert_eq!(inventory["result"]["counts"]["endpoints"], 10000);
            assert_eq!(inventory["coverage"], json!({"status": "partial", "examined": 5001, "total": 5001}));
            assert_eq!(inventory["result"]["capped_inventories"], json!(["endpoints"]));
            assert_eq!(inventory["result"]["rows_limited"], false);
        }
    }
}

#[test]
fn native_empty_captures_remain_complete() {
    for name in ["empty.pcap", "empty.pcapng"] {
        for (tool, params) in [
            ("packets_capture_show", json!({})),
            ("packets_fields_show", json!({})),
            ("packets_inventory_show", json!({"engine": "built_in"})),
        ] {
            let evidence = call(tool, name, false, params);
            assert_eq!(evidence["coverage"], json!({"status": "complete", "examined": 0, "total": 0}));
        }
    }
}
