use std::path::PathBuf;
use std::process::ExitCode;

use clap::Parser;
use zppz_chart_validate::{extract_archive, ErrorPayload, ValidateError};

#[derive(Debug, Parser)]
#[command(
    name = "zppz-chart-validate",
    about = "Sandboxed Majdata archive extract and safety validation"
)]
struct Args {
    /// Path to the uploaded archive (.zip or .7z)
    #[arg(long)]
    archive: PathBuf,

    /// Directory that will receive normalized extracted members
    #[arg(long)]
    output_dir: PathBuf,
}

fn main() -> ExitCode {
    let args = Args::parse();
    match run(args) {
        Ok(()) => ExitCode::SUCCESS,
        Err(err) => {
            let payload = ErrorPayload {
                ok: false,
                error: err.to_string(),
            };
            if let Ok(json) = serde_json::to_string(&payload) {
                println!("{json}");
            }
            eprintln!("{err}");
            ExitCode::from(1)
        }
    }
}

fn run(args: Args) -> Result<(), ValidateError> {
    if !args.archive.is_file() {
        return Err(ValidateError::message("压缩包不存在或不是文件"));
    }
    std::fs::create_dir_all(&args.output_dir)?;
    let extracted = extract_archive(&args.archive, &args.output_dir)?;
    let payload = extracted.into_success_payload();
    println!("{}", serde_json::to_string(&payload)?);
    Ok(())
}
