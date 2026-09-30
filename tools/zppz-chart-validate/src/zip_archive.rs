use std::collections::BTreeMap;
use std::fs::File;
use std::io::BufReader;
use std::path::{Path, PathBuf};

use zip::ZipArchive;

use crate::copy::extract_reader_to_file;
use crate::error::ValidateError;
use crate::extract::{ExtractedArchive, ExtractedFile};
use crate::pathutil::{is_readme_member, validate_member_name};
use crate::select::{
    output_name, select_members, selected_limits, validate_archive_sizes, validate_target_size,
    ArchiveEntry,
};

pub fn extract_zip(archive_path: &Path, destination: &Path) -> Result<ExtractedArchive, ValidateError> {
    let file = File::open(archive_path)?;
    let reader = BufReader::new(file);
    let mut archive = ZipArchive::new(reader)
        .map_err(|err| ValidateError::message(format!("ZIP 压缩包已损坏: {err}")))?;

    let mut entries = Vec::new();
    let mut names = Vec::new();
    let mut has_readme = false;
    for index in 0..archive.len() {
        let file = archive
            .by_index(index)
            .map_err(|err| ValidateError::message(format!("ZIP 压缩包解析失败: {err}")))?;
        if file.is_dir() {
            continue;
        }
        let display_name = String::from_utf8_lossy(file.name_raw()).replace('\\', "/");
        let name = validate_member_name(&display_name)?;
        if is_readme_member(&name) {
            has_readme = true;
        }
        let symlink = file
            .unix_mode()
            .map(|mode| mode & 0o170000 == 0o120000)
            .unwrap_or(false);
        entries.push(ArchiveEntry {
            name: name.clone(),
            uncompressed: file.size(),
            compressed: file.compressed_size(),
            encrypted: file.encrypted(),
            symlink,
        });
        names.push(name);
    }

    validate_archive_sizes(&entries)?;
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

    std::fs::create_dir_all(destination)?;
    let mut files = Vec::new();
    let mut source_members = BTreeMap::new();

    for (kind, member_name) in planned {
        let index = find_member_index(&mut archive, &member_name)?;
        let mut file = archive
            .by_index(index)
            .map_err(|err| ValidateError::message(format!("ZIP 压缩包解析失败: {err}")))?;
        let target_name = output_name(kind, &member_name);
        let target = destination.join(&target_name);
        let max_bytes = selected_limits(kind);
        extract_reader_to_file(&mut file, &target, max_bytes, &member_name)?;
        files.push(ExtractedFile {
            output_name: target_name.clone(),
            relative_path: PathBuf::from(&target_name),
        });
        source_members.insert(target_name, member_name);
    }

    Ok(ExtractedArchive {
        files,
        source_members,
        has_readme,
    })
}

fn find_member_index(
    archive: &mut ZipArchive<BufReader<File>>,
    member_name: &str,
) -> Result<usize, ValidateError> {
    for index in 0..archive.len() {
        let file = archive
            .by_index(index)
            .map_err(|err| ValidateError::message(format!("ZIP 压缩包解析失败: {err}")))?;
        if file.is_dir() {
            continue;
        }
        let display_name = String::from_utf8_lossy(file.name_raw()).replace('\\', "/");
        let name = validate_member_name(&display_name)?;
        if name == member_name {
            return Ok(index);
        }
    }
    Err(ValidateError::message(format!(
        "ZIP 压缩包无法读取 {}",
        crate::pathutil::basename(member_name)
    )))
}
