pub const MAX_ARCHIVE_ENTRIES: usize = 2048;
pub const MAX_MAIDATA_BYTES: u64 = 1024 * 1024;
pub const MAX_COVER_BYTES: u64 = 20 * 1024 * 1024;
pub const MAX_MEMBER_BYTES: u64 = 512 * 1024 * 1024;
pub const MAX_TOTAL_UNCOMPRESSED_BYTES: u64 = 2 * 1024 * 1024 * 1024;
pub const MAX_COMPRESSION_RATIO: u64 = 200;
pub const COPY_CHUNK_BYTES: usize = 1024 * 1024;

pub const COVER_SUFFIXES: &[&str] = &[".png", ".jpg", ".webp"];
pub const AUDIO_SUFFIXES: &[&str] = &[".mp3", ".ogg"];
pub const VIDEO_MEMBER_NAMES: &[&str] = &["bg.mp4", "mv.mp4", "pv.mp4"];
