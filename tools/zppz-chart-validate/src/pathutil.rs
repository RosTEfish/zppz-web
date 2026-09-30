use std::path::{Component, Path};

use crate::error::ValidateError;

pub fn normalize_member_name(name: &str) -> String {
    name.replace('\\', "/")
}

pub fn validate_member_name(name: &str) -> Result<String, ValidateError> {
    let normalized = normalize_member_name(name);
    if normalized.is_empty()
        || normalized.contains('\0')
        || normalized.starts_with('/')
        || looks_like_windows_drive(&normalized)
    {
        return Err(ValidateError::message("压缩包包含绝对路径"));
    }
    let path = Path::new(&normalized);
    for component in path.components() {
        match component {
            Component::Normal(_) => {}
            Component::CurDir | Component::ParentDir | Component::RootDir | Component::Prefix(_) => {
                return Err(ValidateError::message("压缩包包含不安全路径"));
            }
        }
    }
    if normalized.split('/').any(|part| part.is_empty()) {
        return Err(ValidateError::message("压缩包包含不安全路径"));
    }
    Ok(normalized)
}

fn looks_like_windows_drive(name: &str) -> bool {
    let bytes = name.as_bytes();
    bytes.len() >= 2 && bytes[0].is_ascii_alphabetic() && bytes[1] == b':'
}

pub fn basename(name: &str) -> &str {
    Path::new(name)
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or(name)
}

pub fn member_sort_key(name: &str) -> (usize, String) {
    let normalized = normalize_member_name(name);
    let depth = Path::new(&normalized).components().count();
    (depth, normalized.to_ascii_lowercase())
}

pub fn is_readme_member(name: &str) -> bool {
    let base = basename(name).to_ascii_lowercase();
    base == "readme" || base.starts_with("readme.")
}

pub fn public_file_name(kind: &str, original: &str) -> String {
    if kind == "maidata" {
        return "maidata.txt".to_string();
    }
    let suffix = Path::new(original)
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| format!(".{}", value.to_ascii_lowercase()))
        .unwrap_or_default();
    format!("{kind}{suffix}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_traversal_and_absolute_paths() {
        assert!(validate_member_name("../etc/passwd").is_err());
        assert!(validate_member_name("/tmp/x").is_err());
        assert!(validate_member_name("C:/windows").is_err());
        assert!(validate_member_name("nested/../maidata.txt").is_err());
        assert!(validate_member_name("nested/maidata.txt").is_ok());
    }
}
