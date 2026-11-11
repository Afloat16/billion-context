use craft_anything_formats::zip;
use serde::Deserialize;
use serde_json::json;
use sha2::{Digest, Sha256};
use std::{error::Error, fs, hint::black_box, time::Instant};

#[derive(Deserialize)]
struct Case {
    offset: usize,
    len: usize,
}

fn argument(args: &[String], index: usize) -> Result<&str, Box<dyn Error>> {
    args.get(index).map(String::as_str).ok_or_else(|| "missing argument".into())
}

fn main() -> Result<(), Box<dyn Error>> {
    let args: Vec<String> = std::env::args().collect();
    match argument(&args, 1)? {
        "crc" => {
            let corpus = fs::read(argument(&args, 2)?)?;
            let cases: Vec<Case> = serde_json::from_slice(&fs::read(argument(&args, 3)?)?)?;
            let mut outputs = Vec::with_capacity(cases.len());
            for case in cases {
                let end = case.offset.checked_add(case.len).ok_or("case extent overflow")?;
                let bytes = corpus.get(case.offset..end).ok_or("case outside corpus")?;
                outputs.push(zip::crc32(black_box(bytes)));
            }
            println!("{}", serde_json::to_string(&outputs)?);
        }
        "zip" => {
            let archive = fs::read(argument(&args, 2)?)?;
            let expected = fs::read(argument(&args, 3)?)?;
            let iterations: usize = argument(&args, 4)?.parse()?;
            if iterations == 0 {
                return Err("at least one iteration is required".into());
            }
            let listing = zip::parse(&archive, 2)?;
            if listing.entries.len() != 1 || listing.truncated {
                return Err("benchmark requires exactly one complete member".into());
            }
            let entry = listing.entries.first().ok_or("member missing")?;
            if entry.method != 0 || entry.uncompressed_size != expected.len() as u64 {
                return Err("benchmark requires a stored member of the expected length".into());
            }
            for _ in 0..2 {
                let decoded = zip::read_entry(&archive, entry, expected.len() as u64)?;
                if decoded != expected {
                    return Err("warm-up output differs".into());
                }
                black_box(decoded);
            }
            let mut elapsed_ns = 0u128;
            let mut output_sha256 = String::new();
            for iteration in 0..iterations {
                let start = Instant::now();
                let decoded = zip::read_entry(black_box(&archive), black_box(entry), black_box(expected.len() as u64))?;
                black_box(decoded.as_slice());
                elapsed_ns += start.elapsed().as_nanos();
                if decoded != expected {
                    return Err("timed output differs".into());
                }
                if iteration + 1 == iterations {
                    output_sha256 = format!("{:x}", Sha256::digest(&decoded));
                }
            }
            println!(
                "{}",
                json!({
                    "bytes": expected.len(),
                    "iterations": iterations,
                    "elapsed_ns": elapsed_ns,
                    "crc32": entry.crc32,
                    "output_sha256": output_sha256,
                    "all_outputs_equal": true,
                })
            );
        }
        _ => return Err("unknown mode".into()),
    }
    Ok(())
}
