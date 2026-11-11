use std::time::Instant;
use craft_anything_formats::har;

fn main() {
    let args: Vec<_> = std::env::args().collect();
    let bytes = std::fs::read(&args[1]).unwrap();
    let limit: usize = args[2].parse().unwrap();
    let started = Instant::now();
    let capture = har::parse(&bytes, limit).unwrap();
    let elapsed = started.elapsed().as_nanos();
    assert_eq!(capture.declared_entries, 20_000);
    assert_eq!(capture.entries.len(), limit.min(20_000));
    assert_eq!(capture.truncated, limit < 20_000);
    assert_eq!(capture.pages, 3);
    assert_eq!(capture.version.as_deref(), Some("1.2"));
    if let Some(first) = capture.entries.first() {
        assert_eq!(first.request.url, "https://capture.example.test/items/0");
        assert_eq!(first.response.text.as_ref().unwrap().len(), 4096);
        assert_eq!(first.request.headers.len(), 12);
    }
    eprintln!("HAR_PARSE_ELAPSED_NS={elapsed}");
    println!("{capture:?}");
}
