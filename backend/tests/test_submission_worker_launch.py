"""Production ser1 has about 1.6G RAM, so launchers keep one submission worker."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCH_SCRIPT = REPO_ROOT / "scripts" / "run_web_with_worker.sh"
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy_remote.sh"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"


def test_combined_launcher_starts_one_cleanup_submission_worker(tmp_path: Path) -> None:
    log_path = tmp_path / "argv.log"
    fake_python = tmp_path / "python"
    fake_python.write_text(
        "#!/bin/sh\n"
        f"printf '%s cleanup=%s\\n' \"$*\" \"${{SUBMISSION_WORKER_CLEANUP:-unset}}\" >> {log_path}\n"
        "sleep 30\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    env = {
        "PATH": os.environ["PATH"],
        "ZPPZ_PYTHON_BIN": str(fake_python),
        "ZPPZ_APP_PORT": "8000",
        "ZPPZ_WEB_CONCURRENCY": "1",
    }
    bash = shutil.which("bash")
    assert bash is not None
    process = subprocess.Popen(  # noqa: S603
        [bash, str(LAUNCH_SCRIPT)],
        env=env,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 5
        text = ""
        while time.monotonic() < deadline:
            text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
            if "-m uvicorn" in text:
                break
            time.sleep(0.05)
        else:
            raise AssertionError(f"launcher did not reach uvicorn: {text!r}")
    finally:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)

    lines = [line for line in text.splitlines() if line]
    submission = [line for line in lines if line.startswith("-m app.worker ")]
    webhook = [line for line in lines if line.startswith("-m app.webhook_worker ")]
    assert submission == ["-m app.worker cleanup=1"]
    assert webhook == ["-m app.webhook_worker cleanup=unset"]


def test_supervisor_starts_one_submission_worker_and_webhook(monkeypatch) -> None:
    import app.worker_supervisor as supervisor

    supervisor.children.clear()
    calls: list[tuple[list[str], dict[str, str] | None]] = []

    class _Process:
        def __init__(self, args: list[str], env: dict[str, str] | None = None) -> None:
            calls.append((list(args), env))

        def poll(self) -> int:
            return 0

        def terminate(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            return 0

    monkeypatch.setattr(supervisor.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(supervisor.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        supervisor.subprocess,
        "Popen",
        lambda args, env=None, **_kwargs: _Process(args, env),
    )
    try:
        assert supervisor.main() == 0
    finally:
        supervisor.children.clear()

    submission = [env for args, env in calls if args[-2:] == ["-m", "app.worker"]]
    webhook = [args for args, _env in calls if args[-2:] == ["-m", "app.webhook_worker"]]
    assert len(submission) == 1
    assert submission[0] is not None
    assert submission[0]["SUBMISSION_WORKER_CLEANUP"] == "1"
    assert len(webhook) == 1


def test_deploy_expects_one_submission_worker() -> None:
    deploy = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    assert "Expected 2 submission workers" not in deploy
    assert 'if [ "${submission_workers:-0}" -ne 1 ]; then' in deploy
    assert 'echo "Expected 1 submission worker, found ${submission_workers:-0}."' in deploy
    assert "app.webhook_worker" in deploy
    assert "running both submission Workers" not in deploy


def test_compose_defines_one_submission_worker() -> None:
    compose = COMPOSE_FILE.read_text(encoding="utf-8")
    assert compose.count('command: ["python", "-m", "app.worker"]') == 1
    assert 'command: ["python", "-m", "app.webhook_worker"]' in compose
    assert "worker-2:" not in compose
