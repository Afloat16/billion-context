use craft_anything_formats::fsread::{Limits, jffs2};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::io::Read;
use std::path::PathBuf;
use std::time::Instant;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().collect();
    let image_path = args.get(1).ok_or("missing image")?;
    let source = PathBuf::from(args.get(2).ok_or("missing source directory")?);
    let mut limits = Limits::default();
    if let Some(cap) = args.get(3) {
        limits.max_file_bytes = cap.parse()?;
    }
    let input = std::fs::read(image_path)?;
    let started = Instant::now();
    let recovered = jffs2::read(&input, &limits);
    let elapsed_ns = started.elapsed().as_nanos();
    let metadata = serde_json::to_vec(&recovered)?;
    let mut full = Sha256::new();
    full.update((metadata.len() as u64).to_le_bytes());
    full.update(&metadata);
    let mut files = Vec::new();
    let mut compared_bytes = 0u64;
    for entry in &recovered.entries {
        let digest = if let Some(data) = &entry.data {
            full.update([1]);
            full.update((data.len() as u64).to_le_bytes());
            full.update(data);
            let mut file = std::fs::File::open(source.join(&entry.path))?;
            let mut buffer = [0u8; 65536];
            let mut position = 0usize;
            loop {
                let count = file.read(&mut buffer)?;
                if count == 0 {
                    break;
                }
                let end = position.checked_add(count).ok_or("source offset overflow")?;
                if data.get(position..end) != Some(&buffer[..count]) {
                    return Err(format!("recovered bytes differ from source: {}", entry.path).into());
                }
                position = end;
            }
            if position != data.len() {
                return Err(format!("recovered length differs from source: {}", entry.path).into());
            }
            compared_bytes += data.len() as u64;
            Some(format!("{:x}", Sha256::digest(data)))
        } else {
            full.update([0]);
            None
        };
        files.push(json!({
            "path": entry.path,
            "data_len": entry.data.as_ref().map(Vec::len),
            "sha256": digest,
        }));
    }
    println!("{}", json!({
        "elapsed_ns": elapsed_ns,
        "input_bytes": input.len(),
        "image": recovered,
        "files": files,
        "compared_bytes": compared_bytes,
        "complete_output_sha256": format!("{:x}", full.finalize()),
    }));
    Ok(())
}
