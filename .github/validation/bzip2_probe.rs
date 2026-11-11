use craft_anything_formats::decompress;
use serde_json::{Value, json};
use std::io::{self, Read};

fn main() {
    let mut text = String::new();
    io::stdin().read_to_string(&mut text).unwrap();
    let case: Value = serde_json::from_str(&text).unwrap();
    let bytes: Vec<u8> = case["input"].as_array().unwrap().iter().map(|v| v.as_u64().unwrap() as u8).collect();
    let cap = case["cap"].as_u64().unwrap();
    let result = match decompress::bzip2(&bytes, cap) {
        Ok(bytes) => json!({"kind": "ok", "bytes": bytes}),
        Err(decompress::DecompressError::TooLarge) => json!({"kind": "too_large"}),
        Err(decompress::DecompressError::Truncated) => json!({"kind": "corrupt"}),
        Err(decompress::DecompressError::Corrupt) => json!({"kind": "corrupt"}),
    };
    println!("{result}");
}
