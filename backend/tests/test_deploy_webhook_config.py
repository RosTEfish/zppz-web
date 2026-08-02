import ast
from pathlib import Path
import re


WEBHOOK_STORAGE_KEYS = {
    "WEBHOOK_SIGNING_MASTER_KEY",
    "PUBLIC_BASE_URL",
    "WEBHOOK_SCAN_INTERVAL_SECONDS",
    "WEBHOOK_ASSET_URL_TTL_SECONDS",
    "WEBHOOK_ASSET_RETENTION_DAYS",
}


def test_deploy_script_accepts_every_webhook_storage_key_written_by_ci():
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (repo_root / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    deploy_script = (repo_root / "scripts" / "deploy_remote.sh").read_text(encoding="utf-8")
    match = re.search(r"^\s+(OBJECT_STORAGE_BACKEND\|[^\n]+)\)$", deploy_script, re.MULTILINE)
    assert match, "storage configuration allowlist was not found"
    allowed = set(match.group(1).split("|"))

    for key in WEBHOOK_STORAGE_KEYS:
        assert f"{key}=" in workflow, f"CI does not write {key}"
        assert key in allowed, f"deploy script rejects CI storage key {key}"


def test_deploy_health_check_allows_bounded_cold_start():
    repo_root = Path(__file__).resolve().parents[2]
    deploy_script = (repo_root / "scripts" / "deploy_remote.sh").read_text(encoding="utf-8")

    assert "deadline = time.monotonic() + 60" in deploy_script
    assert "time.sleep(min(2, remaining))" in deploy_script
    assert "health check passed" in deploy_script
    health_script = deploy_script.split('if ! "$venv_dir/bin/python" - <<PY\n', 1)[1].split("\nPY\nthen", 1)[0]
    ast.parse(health_script.replace("$APP_PORT", "8000"))
