use craft_anything_formats::{decompress::{self, DecompressError}, zip};

// Produced independently with CPython's native libbz2, compression levels 1 and 9.
const EMPTY: &[u8] = &[66, 90, 104, 57, 23, 114, 69, 56, 80, 144, 0, 0, 0, 0];
const ASCII: &[u8] = &[66, 90, 104, 49, 49, 65, 89, 38, 83, 89, 188, 222, 16, 152, 0, 0, 2, 221, 128, 0, 16, 64, 1, 16, 0, 1, 0, 18, 34, 92, 16, 32, 0, 49, 0, 0, 8, 2, 97, 162, 46, 184, 16, 37, 47, 176, 70, 170, 95, 79, 197, 220, 145, 78, 20, 36, 47, 55, 132, 38, 0];
const UNICODE: &[u8] = &[66, 90, 104, 57, 49, 65, 89, 38, 83, 89, 214, 103, 54, 123, 0, 0, 9, 208, 121, 128, 16, 64, 0, 0, 68, 96, 64, 128, 148, 0, 80, 7, 128, 64, 0, 32, 0, 49, 77, 50, 49, 49, 49, 10, 0, 200, 105, 226, 143, 161, 25, 27, 93, 128, 138, 145, 170, 5, 124, 93, 201, 20, 225, 66, 67, 89, 156, 217, 236];
const FIRST: &[u8] = b"First bzip2 member.\n";
const SECOND: &[u8] = "第二个成员 🧪\n".as_bytes();

fn joined(parts: &[&[u8]]) -> Vec<u8> { parts.concat() }

#[test]
fn reads_native_single_members_including_empty_and_unicode() {
    for (frame, plain) in [(EMPTY, &b""[..]), (ASCII, FIRST), (UNICODE, SECOND)] {
        assert_eq!(decompress::bzip2(frame, plain.len() as u64).unwrap(), plain);
    }
}

#[test]
fn joins_different_members_and_keeps_empty_members_in_every_position() {
    let plain = joined(&[FIRST, SECOND]);
    for frames in [
        vec![ASCII, UNICODE],
        vec![EMPTY, ASCII, UNICODE],
        vec![ASCII, EMPTY, UNICODE],
        vec![ASCII, UNICODE, EMPTY],
    ] {
        assert_eq!(decompress::bzip2(&joined(&frames), 1000).unwrap(), plain);
    }
    assert_eq!(decompress::bzip2(&joined(&[EMPTY, ASCII]), 1000).unwrap(), FIRST);
}

#[test]
fn all_members_share_the_same_output_budget() {
    let frames = joined(&[ASCII, UNICODE]);
    let plain = joined(&[FIRST, SECOND]);
    assert_eq!(decompress::bzip2(&frames, plain.len() as u64).unwrap(), plain);
    for cap in [0, FIRST.len(), plain.len() - 1] {
        assert_eq!(decompress::bzip2(&frames, cap as u64), Err(DecompressError::TooLarge));
    }
    assert_eq!(decompress::bzip2(&joined(&[EMPTY, ASCII]), 0), Err(DecompressError::TooLarge));
}

#[test]
fn damaged_later_members_do_not_return_a_successful_prefix() {
    for offset in [10, UNICODE.len() - 2] {
        let mut bad = UNICODE.to_vec();
        bad[offset] ^= 1;
        assert_eq!(decompress::bzip2(&joined(&[ASCII, &bad]), 1000), Err(DecompressError::Corrupt));
    }
    let mut bad_empty = EMPTY.to_vec();
    *bad_empty.last_mut().unwrap() ^= 1;
    assert_eq!(decompress::bzip2(&joined(&[ASCII, &bad_empty]), 1000), Err(DecompressError::Corrupt));
}

#[test]
fn every_incomplete_later_member_is_rejected() {
    for end in 1..UNICODE.len() {
        assert_eq!(decompress::bzip2(&joined(&[ASCII, &UNICODE[..end]]), 1000), Err(DecompressError::Corrupt), "prefix {end}");
    }
}

#[test]
fn corrupted_first_members_still_fail() {
    let mut bad = ASCII.to_vec();
    bad[10] ^= 1;
    assert_eq!(decompress::bzip2(&bad, 1000), Err(DecompressError::Corrupt));
    assert_eq!(decompress::bzip2(&joined(&[&bad, UNICODE]), 1000), Err(DecompressError::Corrupt));
}

#[test]
fn trailing_non_member_bytes_do_not_hide_valid_members() {
    for tail in [&b"trailing firmware data"[..], &b"\0\0\0\0"[..], &b"BZh0"[..], &b"BZhA"[..]] {
        assert_eq!(decompress::bzip2(&joined(&[ASCII, tail]), 1000).unwrap(), FIRST);
        assert_eq!(decompress::bzip2(&joined(&[ASCII, UNICODE, tail]), 1000).unwrap(), joined(&[FIRST, SECOND]));
    }
}

#[test]
fn empty_members_need_no_output_budget() {
    for count in 1..5 {
        let frames = EMPTY.repeat(count);
        assert_eq!(decompress::bzip2(&frames, 0).unwrap(), b"");
    }
}

#[test]
fn empty_or_non_bzip2_input_is_not_a_complete_stream() {
    for input in [&b""[..], &b"invalid"[..], &b"BZ"[..]] {
        assert!(decompress::bzip2(input, 1000).is_err());
    }
}

fn zip_member(frame: &[u8], plain: &[u8]) -> Vec<u8> {
    let name = b"fixture.bin";
    let crc = zip::crc32(plain);
    let compressed = u32::try_from(frame.len()).unwrap();
    let size = u32::try_from(plain.len()).unwrap();
    let mut out = Vec::new();
    out.extend_from_slice(b"PK\x03\x04");
    for value in [46u16, 0, 12, 0, 0] {
        out.extend_from_slice(&value.to_le_bytes());
    }
    for value in [crc, compressed, size] {
        out.extend_from_slice(&value.to_le_bytes());
    }
    for value in [name.len() as u16, 0] {
        out.extend_from_slice(&value.to_le_bytes());
    }
    out.extend_from_slice(name);
    out.extend_from_slice(frame);
    let directory = u32::try_from(out.len()).unwrap();
    out.extend_from_slice(b"PK\x01\x02");
    for value in [46u16, 46, 0, 12, 0, 0] {
        out.extend_from_slice(&value.to_le_bytes());
    }
    for value in [crc, compressed, size] {
        out.extend_from_slice(&value.to_le_bytes());
    }
    for value in [name.len() as u16, 0, 0, 0, 0] {
        out.extend_from_slice(&value.to_le_bytes());
    }
    for value in [0u32, 0] {
        out.extend_from_slice(&value.to_le_bytes());
    }
    out.extend_from_slice(name);
    let directory_size = u32::try_from(out.len()).unwrap() - directory;
    out.extend_from_slice(b"PK\x05\x06");
    for value in [0u16, 0, 1, 1] {
        out.extend_from_slice(&value.to_le_bytes());
    }
    out.extend_from_slice(&directory_size.to_le_bytes());
    out.extend_from_slice(&directory.to_le_bytes());
    out.extend_from_slice(&0u16.to_le_bytes());
    out
}

#[test]
fn zip_method_twelve_reads_every_member_and_preserves_crc_and_limits() {
    let frames = joined(&[ASCII, EMPTY, UNICODE]);
    let plain = joined(&[FIRST, SECOND]);
    let bytes = zip_member(&frames, &plain);
    let archive = zip::parse(&bytes, 10).unwrap();
    assert_eq!(archive.entries.len(), 1);
    assert_eq!(zip::read_entry(&bytes, &archive.entries[0], plain.len() as u64).unwrap(), plain);
    assert!(zip::read_entry(&bytes, &archive.entries[0], plain.len() as u64 - 1).is_err());
    let wrong_crc = zip_member(&frames, b"different complete content");
    let archive = zip::parse(&wrong_crc, 10).unwrap();
    assert!(zip::read_entry(&wrong_crc, &archive.entries[0], 1000).is_err());
}
