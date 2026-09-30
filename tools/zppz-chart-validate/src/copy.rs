use std::fs::File;
use std::io::{Read, Write};
use std::path::Path;

use crate::error::ValidateError;
use crate::limits::COPY_CHUNK_BYTES;
use crate::pathutil::basename;

pub fn copy_limited<R: Read + ?Sized, W: Write + ?Sized>(
    source: &mut R,
    destination: &mut W,
    max_bytes: u64,
    label: &str,
) -> Result<u64, ValidateError> {
    let mut buffer = vec![0_u8; COPY_CHUNK_BYTES];
    let mut written = 0_u64;
    loop {
        let read = source.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        written = written.saturating_add(read as u64);
        if written > max_bytes {
            return Err(ValidateError::message(format!(
                "{} 大小超出限制",
                basename(label)
            )));
        }
        destination.write_all(&buffer[..read])?;
    }
    Ok(written)
}

pub fn extract_reader_to_file<R: Read>(
    source: &mut R,
    target: &Path,
    max_bytes: u64,
    label: &str,
) -> Result<u64, ValidateError> {
    if let Some(parent) = target.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let mut file = File::create(target)?;
    let written = copy_limited(source, &mut file, max_bytes, label)?;
    file.flush()?;
    Ok(written)
}
