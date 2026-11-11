use craft_anything_formats::decompress::{self, DecompressError};
use serde::Deserialize;
use serde_json::json;

#[derive(Deserialize)]
struct Case {
    name: String,
    frame: Vec<u8>,
    cap: u64,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cases: Vec<Case> = serde_json::from_reader(std::io::stdin().lock())?;
    let results: Vec<_> = cases
        .into_iter()
        .map(|case| match decompress::zstd(&case.frame, case.cap) {
            Ok(bytes) => json!({"name": case.name, "status": "ok", "bytes": bytes}),
            Err(error) => {
                let status = match error {
                    DecompressError::Corrupt => "corrupt",
                    DecompressError::Truncated => "truncated",
                    DecompressError::TooLarge => "too_large",
                };
                json!({"name": case.name, "status": status})
            }
        })
        .collect();
    println!("{}", serde_json::to_string(&results)?);
    Ok(())
}
