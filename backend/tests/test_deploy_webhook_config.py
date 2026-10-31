import ast
import re
from pathlib import Path

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


def test_validation_runs_on_pull_requests_and_deploy_reuses_artifacts():
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (repo_root / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")

    assert "pull_request:" in workflow
    assert "vars.DEPLOY_PORT || '22'" in workflow
    assert "secrets.DEPLOY_PORT" not in workflow
    assert "github.event_name != 'pull_request'" in workflow
    assert "success() && github.event_name != 'pull_request'" in workflow
    assert "Swatinem/rust-cache@d1527c8f67ef9af357290475d4af4b0fab8f12e0 # v2" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "actions/download-artifact@v4" in workflow
    assert workflow.count("npm run build") == 1
    assert workflow.count("build_chart_validate.sh") == 1
    assert workflow.count("dtolnay/rust-toolchain@b725eda525362e7cf34af9a7243cac1e3f01a7ec # stable") == 1
    assert "cargo test --manifest-path tools/zppz-chart-validate/Cargo.toml" in workflow


def _active_config_lines(text: str) -> str:
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        kept.append(stripped)
    return "\n".join(kept)


def test_frontend_release_ships_precompressed_assets():
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (repo_root / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    dockerfile = (repo_root / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    deploy_script = (repo_root / "scripts" / "deploy_remote.sh").read_text(encoding="utf-8")
    docker_nginx = (repo_root / "infra" / "nginx" / "default.conf").read_text(encoding="utf-8")
    sample = (repo_root / "infra" / "nginx" / "precompressed.conf.sample").read_text(encoding="utf-8")
    package_json = (repo_root / "frontend" / "package.json").read_text(encoding="utf-8")
    script = (repo_root / "frontend" / "scripts" / "precompress-dist.mjs").read_text(encoding="utf-8")

    assert '"precompress": "node scripts/precompress-dist.mjs"' in package_json
    assert "npm run precompress" in workflow
    assert workflow.index("npm run precompress") < workflow.index("name: Upload validated frontend")
    assert "frontend/dist/index.html.gz" in workflow
    assert "frontend/dist/index.html.br" in workflow
    assert "npm run precompress" in dockerfile
    assert "gzip -9" not in dockerfile
    assert "zstd" not in dockerfile.lower()
    assert "zstd" not in _active_config_lines(sample).lower()
    assert "zstd" not in _active_config_lines(docker_nginx).lower()
    assert "zstdCompress" not in script
    assert "gzip_static on;" in _active_config_lines(docker_nginx)
    assert "brotli_static" not in _active_config_lines(docker_nginx)
    assert "gzip_static on;" in _active_config_lines(sample)
    assert "brotli_static on;" in _active_config_lines(sample)
    assert "ngx_brotli" in sample
    assert 'chmod a+x "$app_dir/frontend"' in deploy_script
    assert 'chmod -R a+rX "$app_dir/frontend/dist"' in deploy_script


def test_deploy_health_check_allows_bounded_cold_start():
    repo_root = Path(__file__).resolve().parents[2]
    deploy_script = (repo_root / "scripts" / "deploy_remote.sh").read_text(encoding="utf-8")

    assert "deadline = time.monotonic() + 60" in deploy_script
    assert "time.sleep(min(2, remaining))" in deploy_script
    assert "health check passed" in deploy_script
    health_script = deploy_script.split('if ! "$venv_dir/bin/python" - <<PY\n', 1)[1].split("\nPY\nthen", 1)[0]
    ast.parse(health_script.replace("$APP_PORT", "8000"))
