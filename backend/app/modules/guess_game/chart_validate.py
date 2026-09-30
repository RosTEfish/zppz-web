from __future__ import annotations

from dataclasses import replace
import json
import logging
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

from app.modules.guess_game.importer import (
    ArchiveParseError,
    PreparedArchive,
    _prepared_result,
)

logger = logging.getLogger(__name__)

SUPPORTED_RUST_SUFFIXES = {".zip", ".7z"}


def resolve_chart_validate_bin() -> Path | None:
    """Locate the sandboxed archive validator binary when it is available."""
    configured = os.getenv("ZPPZ_CHART_VALIDATE_BIN", "").strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))
    which = shutil.which("zppz-chart-validate")
    if which:
        candidates.append(Path(which))
    backend_root = Path(__file__).resolve().parents[3]
    candidates.append(backend_root / "bin" / "zppz-chart-validate")
    repo_root = backend_root.parent
    candidates.append(
        repo_root / "tools" / "zppz-chart-validate" / "target" / "release" / "zppz-chart-validate"
    )
    candidates.append(
        repo_root / "tools" / "zppz-chart-validate" / "target" / "debug" / "zppz-chart-validate"
    )
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def rust_prepare_available(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_RUST_SUFFIXES and resolve_chart_validate_bin() is not None


def prepare_archive_with_rust(
    path: Path,
    destination: Path,
    *,
    timeout_seconds: int | None = None,
) -> PreparedArchive:
    """Extract and safety-check an archive in a killable Rust subprocess."""
    binary = resolve_chart_validate_bin()
    if binary is None:
        raise ArchiveParseError("未找到 zppz-chart-validate 可执行文件")
    if path.suffix.lower() not in SUPPORTED_RUST_SUFFIXES:
        raise ArchiveParseError("Rust 校验器当前仅支持 zip/7z")

    destination.mkdir(parents=True, exist_ok=True)
    limit = timeout_seconds
    if limit is None:
        limit = int(os.getenv("SUBMISSION_VALIDATION_TIMEOUT_SECONDS", str(5 * 60)))

    command = [
        str(binary),
        "--archive",
        str(path),
        "--output-dir",
        str(destination),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=limit,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired as exc:
        _kill_process_group(exc)
        raise ArchiveParseError(
            f"谱面校验超时（超过 {limit} 秒），请检查压缩包后重新上传"
        ) from exc
    except OSError as exc:
        raise ArchiveParseError(f"无法启动谱面校验进程: {exc}") from exc

    payload = _parse_cli_payload(completed.stdout)
    if completed.returncode != 0 or not payload.get("ok"):
        message = str(payload.get("error") or "").strip()
        if not message:
            message = (completed.stderr or completed.stdout or "谱面校验失败").strip()
        raise ArchiveParseError(message)

    files = {
        name: destination / relative
        for name, relative in dict(payload.get("files") or {}).items()
    }
    if "maidata.txt" not in files:
        raise ArchiveParseError("压缩包缺少 maidata.txt")
    prepared = _prepared_result(path, files)
    return PreparedArchive(
        replace(prepared.parsed, has_readme=bool(payload.get("has_readme"))),
        prepared.files,
    )


def _parse_cli_payload(stdout: str) -> dict:
    text = (stdout or "").strip()
    if not text:
        return {"ok": False, "error": "谱面校验进程没有返回结果"}
    line = text.splitlines()[-1]
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return {"ok": False, "error": "谱面校验进程返回了无法解析的结果"}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "谱面校验进程返回了无法解析的结果"}
    return payload


def _kill_process_group(exc: subprocess.TimeoutExpired) -> None:
    process = getattr(exc, "process", None)
    if process is None or process.pid is None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            process.kill()
        except (ProcessLookupError, PermissionError, OSError):
            logger.warning(
                "failed to kill timed-out chart validate pid=%s",
                process.pid,
                exc_info=True,
            )


def ensure_built_for_tests() -> Path | None:
    """Best-effort local build helper used by optional Rust-backed pytest cases."""
    existing = resolve_chart_validate_bin()
    if existing is not None:
        return existing
    repo_root = Path(__file__).resolve().parents[4]
    crate = repo_root / "tools" / "zppz-chart-validate"
    if not (crate / "Cargo.toml").is_file():
        return None
    cargo = shutil.which("cargo")
    if not cargo:
        return None
    completed = subprocess.run(
        [cargo, "build", "--release"],
        cwd=crate,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr or completed.stdout or "cargo build failed\n")
        return None
    return resolve_chart_validate_bin()
