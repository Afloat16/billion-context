use craft_anything_formats::go;
use serde_json::json;
use std::collections::BTreeMap;

fn main() {
    let path = std::env::args().nth(1).expect("input executable path");
    let bytes = std::fs::read(path).expect("read fixture");
    let mut report = go::inspect(&bytes, None).expect("inspect real ELF");
    let mut diagnostic_counts = BTreeMap::<String, usize>::new();
    for warning in std::mem::take(&mut report.warnings) {
        *diagnostic_counts.entry(warning).or_default() += 1;
    }
    serde_json::to_writer(std::io::stdout(), &json!({"report": report, "diagnostic_counts": diagnostic_counts})).expect("write report");
    println!();
}
