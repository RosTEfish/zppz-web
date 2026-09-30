use std::collections::BTreeMap;
use std::path::PathBuf;

use serde::Serialize;

use crate::error::ValidateError;
use crate::sevenz_archive::extract_sevenz;
use crate::zip_archive::extract_zip;

#[derive(Debug, Clone, Serialize)]
pub struct ExtractedFile {
    pub output_name: String,
    pub relative_path: PathBuf,
}

#[derive(Debug, Clone)]
pub struct ExtractedArchive {
    pub files: Vec<ExtractedFile>,
    pub source_members: BTreeMap<String, String>,
    pub has_readme: bool,
}

#[derive(Debug, Serialize)]
pub struct SuccessPayload {
    pub ok: bool,
    pub files: BTreeMap<String, String>,
    pub source_members: BTreeMap<String, String>,
    pub has_readme: bool,
}

#[derive(Debug, Serialize)]
pub struct ErrorPayload {
    pub ok: bool,
    pub error: String,
}

pub fn extract_archive(
    archive_path: &std::path::Path,
    destination: &std::path::Path,
) -> Result<ExtractedArchive, ValidateError> {
    let suffix = archive_path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    match suffix.as_str() {
        "zip" => extract_zip(archive_path, destination),
        "7z" => extract_sevenz(archive_path, destination),
        "rar" => Err(ValidateError::message(
            "RAR 请使用 Python 回退路径；zppz-chart-validate 当前支持 zip/7z",
        )),
        _ => Err(ValidateError::message("仅支持 zip、7z、rar 压缩包")),
    }
}

impl ExtractedArchive {
    pub fn into_success_payload(self) -> SuccessPayload {
        let files = self
            .files
            .into_iter()
            .map(|file| {
                (
                    file.output_name.clone(),
                    file.relative_path.to_string_lossy().replace('\\', "/"),
                )
            })
            .collect();
        SuccessPayload {
            ok: true,
            files,
            source_members: self.source_members,
            has_readme: self.has_readme,
        }
    }
}
