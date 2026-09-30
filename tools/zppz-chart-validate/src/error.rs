use thiserror::Error;

#[derive(Debug, Error)]
pub enum ValidateError {
    #[error("{0}")]
    Message(String),
    #[error(transparent)]
    Io(#[from] std::io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
}

impl ValidateError {
    pub fn message(text: impl Into<String>) -> Self {
        Self::Message(text.into())
    }
}
