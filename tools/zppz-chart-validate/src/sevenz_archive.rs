use std::collections::{BTreeMap, BTreeSet};
use std::fs::File;
use std::path::{Path, PathBuf};

use sevenz_rust2::{ArchiveReader, Password};

use crate::copy::copy_limited;
use crate::error::ValidateError;
use crate::extract::{ExtractedArchive, ExtractedFile};
use crate::pathutil::{basename, is_readme_member, validate_member_name};
use crate::select::{
    output_name, select_members, selected_limits, validate_archive_sizes,
    validate_overall_compression_ratio, validate_target_size, ArchiveEntry,
};

pub fn extract_sevenz(
    archive_path: &Path,
    destination: &Path,
) -> Result<ExtractedArchive, ValidateError> {
    let mut reader = ArchiveReader::open(archive_path, Password::empty()).map_err(map_sevenz_error)?;
    // Keep extraction single-threaded so resource use stays predictable for untrusted input.
    reader.set_thread_count(1);

    let archive_bytes = std::fs::metadata(archive_path)?.len();
    let listed: Vec<(String, u64, u64, bool)> = reader
        .archive()
        .files
        .iter()
        .map(|entry| {
            (
                entry.name().to_string(),
                entry.size(),
                entry.compressed_size,
                entry.is_directory(),
            )
        })
        .collect();

    let mut entries = Vec::new();
    let mut names = Vec::new();
    let mut has_readme = false;
    let mut total_uncompressed = 0_u64;

    for (raw_name, uncompressed, compressed_size, is_directory) in listed {
        if is_directory {
            continue;
        }
        let name = validate_member_name(&raw_name)?;
        if is_readme_member(&name) {
            has_readme = true;
        }
        let compressed = if compressed_size > 0 {
            compressed_size
        } else {
            uncompressed.max(1)
        };
        total_uncompressed = total_uncompressed.saturating_add(uncompressed);
        entries.push(ArchiveEntry {
            name: name.clone(),
            uncompressed,
            compressed,
            encrypted: false,
            symlink: false,
        });
        names.push(name);
    }

    validate_archive_sizes(&entries)?;
    validate_overall_compression_ratio(total_uncompressed, archive_bytes)?;
    let selected = select_members(&names)?;
    let by_name: BTreeMap<_, _> = entries
        .into_iter()
        .map(|entry| (entry.name.clone(), entry))
        .collect();

    validate_target_size(
        &selected.maidata,
        by_name[&selected.maidata].uncompressed,
        selected_limits("maidata"),
    )?;
    validate_target_size(
        &selected.cover,
        by_name[&selected.cover].uncompressed,
        selected_limits("bg"),
    )?;

    let mut planned = vec![
        ("maidata", selected.maidata.clone()),
        ("track", selected.track.clone()),
        ("bg", selected.cover.clone()),
    ];
    if let Some(video) = selected.video.clone() {
        planned.push(("video", video));
    }

    let wanted: BTreeSet<String> = planned.iter().map(|(_, name)| name.clone()).collect();
    let kind_by_member: BTreeMap<String, &str> = planned
        .iter()
        .map(|(kind, name)| (name.clone(), *kind))
        .collect();

    std::fs::create_dir_all(destination)?;
    let mut files = Vec::new();
    let mut source_members = BTreeMap::new();
    let mut remaining = wanted.clone();

    reader
        .for_each_entries(|entry, source| {
            if entry.is_directory() {
                return Ok(true);
            }
            let name = match validate_member_name(entry.name()) {
                Ok(value) => value,
                Err(_) => return Ok(true),
            };
            if !wanted.contains(&name) {
                // Drain unwanted solid-archive data without materializing it.
                let mut sink = std::io::sink();
                std::io::copy(source, &mut sink)?;
                return Ok(true);
            }
            let kind = kind_by_member.get(&name).copied().unwrap_or("track");
            let target_name = output_name(kind, &name);
            let target = destination.join(&target_name);
            if let Some(parent) = target.parent() {
                std::fs::create_dir_all(parent)?;
            }
            let mut out = File::create(&target)?;
            if let Err(err) = copy_limited(source, &mut out, selected_limits(kind), &name) {
                return Err(std::io::Error::other(err.to_string()).into());
            }
            remaining.remove(&name);
            files.push(ExtractedFile {
                output_name: target_name.clone(),
                relative_path: PathBuf::from(&target_name),
            });
            source_members.insert(target_name, name);
            Ok(true)
        })
        .map_err(map_sevenz_error)?;

    if !remaining.is_empty() {
        let missing = remaining.iter().next().map(|name| basename(name)).unwrap_or("file");
        return Err(ValidateError::message(format!(
            "7z 压缩包无法读取 {missing}"
        )));
    }

    Ok(ExtractedArchive {
        files,
        source_members,
        has_readme,
    })
}

fn map_sevenz_error(err: sevenz_rust2::Error) -> ValidateError {
    let text = err.to_string();
    if text.contains("Password") || text.contains("password") {
        return ValidateError::message("不支持加密压缩包");
    }
    ValidateError::message(format!("7z 压缩包解析失败: {text}"))
}
