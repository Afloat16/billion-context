use craft_anything_engine::{CallOptions, Caller, Engine, ToolOutput};
use serde_json::json;

fn main() {
    for path in std::env::args().skip(1) {
        let data = std::fs::read(&path).unwrap();
        let core = craft_anything_formats::elf::parse_core(&data).unwrap();
        let engine = Engine::new(craft_anything_engine::testing::session());
        let result = engine.call("native_crash_show", json!({"path": path, "with_debugger_context": false}), CallOptions::new(Caller::Cli)).unwrap();
        let evidence = match result {
            ToolOutput::Evidence(value) => {
                assert!(value.verify());
                serde_json::to_value(value).unwrap()
            }
            other => panic!("expected crash evidence, got {other:?}"),
        };
        println!("{}", json!({
            "file": std::path::Path::new(&path).file_name().unwrap().to_str().unwrap(),
            "signal": core.signal,
            "tool_signal": evidence["result"]["signal"],
            "summary": evidence["summary"],
            "fault_location": evidence["result"]["fault_location"],
        }));
    }
}
