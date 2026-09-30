use std::path::Path;

use crate::error::ValidateError;
use crate::limits::{
    AUDIO_SUFFIXES, COVER_SUFFIXES, MAX_ARCHIVE_ENTRIES, MAX_COMPRESSION_RATIO, MAX_COVER_BYTES,
    MAX_MAIDATA_BYTES, MAX_MEMBER_BYTES, MAX_TOTAL_UNCOMPRESSED_BYTES, VIDEO_MEMBER_NAMES,
};
use crate::pathutil::{basename, member_sort_key, public_file_name, validate_member_name};

#[derive(Debug, Clone)]
pub struct ArchiveEntry {
    pub name: String,
    pub uncompressed: u64,
    pub compressed: u64,
    pub encrypted: bool,
    pub symlink: bool,
}

#[derive(Debug, Clone)]
pub struct SelectedMembers {
    pub maidata: String,
    pub track: String,
    pub cover: String,
    pub video: Option<String>,
}

pub fn validate_archive_sizes(entries: &[ArchiveEntry]) -> Result<(), ValidateError> {
    if entries.len() > MAX_ARCHIVE_ENTRIES {
        return Err(ValidateError::message(format!(
            "压缩包文件数量不能超过 {MAX_ARCHIVE_ENTRIES}"
        )));
    }
    let mut total = 0_u64;
    for entry in entries {
        validate_member_name(&entry.name)?;
        if entry.encrypted {
            return Err(ValidateError::message("不支持加密压缩包"));
        }
        if entry.symlink {
            return Err(ValidateError::message("archive cannot contain symbolic links"));
        }
        if entry.uncompressed > MAX_MEMBER_BYTES {
            return Err(ValidateError::message(format!(
                "{} 大小超出限制",
                basename(&entry.name)
            )));
        }
        total = total.saturating_add(entry.uncompressed);
        if total > MAX_TOTAL_UNCOMPRESSED_BYTES {
            return Err(ValidateError::message("压缩包解压后总大小超出限制"));
        }
        if entry.uncompressed > 0
            && (entry.compressed == 0
                || entry.uncompressed / entry.compressed.max(1) > MAX_COMPRESSION_RATIO)
        {
            return Err(ValidateError::message(format!(
                "{} 压缩倍率过高",
                basename(&entry.name)
            )));
        }
    }
    Ok(())
}

pub fn validate_overall_compression_ratio(
    total_uncompressed: u64,
    archive_bytes: u64,
) -> Result<(), ValidateError> {
    if total_uncompressed > 0
        && total_uncompressed / archive_bytes.max(1) > MAX_COMPRESSION_RATIO
    {
        return Err(ValidateError::message("7z 压缩包总压缩倍率过高"));
    }
    Ok(())
}

pub fn select_members(names: &[String]) -> Result<SelectedMembers, ValidateError> {
    if names.len() > MAX_ARCHIVE_ENTRIES {
        return Err(ValidateError::message(format!(
            "压缩包文件数量不能超过 {MAX_ARCHIVE_ENTRIES}"
        )));
    }
    let normalized = names
        .iter()
        .map(|name| validate_member_name(name))
        .collect::<Result<Vec<_>, _>>()?;

    let maidata_names: Vec<_> = normalized
        .iter()
        .filter(|name| basename(name).eq_ignore_ascii_case("maidata.txt"))
        .cloned()
        .collect();
    if maidata_names.is_empty() {
        return Err(ValidateError::message("压缩包缺少 maidata.txt"));
    }
    let maidata = maidata_names
        .into_iter()
        .min_by_key(|name| member_sort_key(name))
        .expect("non-empty");

    let mut cover_names = Vec::new();
    let mut track_names = Vec::new();
    for name in &normalized {
        let base = basename(name);
        let path = Path::new(base);
        let stem = path
            .file_stem()
            .and_then(|value| value.to_str())
            .unwrap_or("")
            .to_ascii_lowercase();
        let suffix = path
            .extension()
            .and_then(|value| value.to_str())
            .map(|value| format!(".{}", value.to_ascii_lowercase()))
            .unwrap_or_default();
        if stem == "bg" && COVER_SUFFIXES.contains(&suffix.as_str()) {
            cover_names.push(name.clone());
        }
        if stem == "track" && AUDIO_SUFFIXES.contains(&suffix.as_str()) {
            track_names.push(name.clone());
        }
    }
    if cover_names.is_empty() {
        return Err(ValidateError::message(
            "压缩包缺少 bg.jpg、bg.png 或 bg.webp",
        ));
    }
    if track_names.is_empty() {
        return Err(ValidateError::message("压缩包缺少 track.mp3 或 track.ogg"));
    }
    let cover = cover_names
        .into_iter()
        .min_by_key(|name| member_sort_key(name))
        .expect("non-empty");
    let track = track_names
        .into_iter()
        .min_by_key(|name| member_sort_key(name))
        .expect("non-empty");
    Ok(SelectedMembers {
        maidata,
        track,
        cover,
        video: select_video_member(&normalized),
    })
}

fn select_video_member(names: &[String]) -> Option<String> {
    let mut priorities = std::collections::HashMap::new();
    for (index, name) in VIDEO_MEMBER_NAMES.iter().enumerate() {
        priorities.insert((*name).to_string(), index);
    }
    let mut candidates = Vec::new();
    for name in names {
        let base = basename(name).to_ascii_lowercase();
        if priorities.contains_key(&base) {
            candidates.push(name.clone());
        }
    }
    candidates.into_iter().min_by_key(|name| {
        let base = basename(name).to_ascii_lowercase();
        let priority = *priorities.get(&base).unwrap_or(&usize::MAX);
        (priority, member_sort_key(name))
    })
}

pub fn validate_target_size(name: &str, size: u64, maximum: u64) -> Result<(), ValidateError> {
    if size > maximum {
        return Err(ValidateError::message(format!(
            "{} 大小超出限制",
            basename(name)
        )));
    }
    Ok(())
}

pub fn selected_limits(kind: &str) -> u64 {
    match kind {
        "maidata" => MAX_MAIDATA_BYTES,
        "bg" => MAX_COVER_BYTES,
        _ => MAX_MEMBER_BYTES,
    }
}

pub fn output_name(kind: &str, member_name: &str) -> String {
    if kind == "video" {
        return basename(member_name).to_ascii_lowercase();
    }
    public_file_name(kind, member_name)
}
