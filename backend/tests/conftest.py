import atexit
import os
from pathlib import Path
import shutil
import tempfile

import pytest


TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="zppz-tests-"))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DATA_DIR"] = str(TEST_DATA_DIR)
os.environ["ADMIN_SEED_PASSWORD"] = "change-me-please"


@pytest.fixture(scope="session", autouse=True)
def prepare_bundled_assets() -> None:
    # Production deployment runs this via ``python -m app.prepare`` before
    # workers start; mirror that one-time step for the isolated test data dir.
    from app.prepare import sync_bundled_assets

    sync_bundled_assets()


@atexit.register
def cleanup_test_data() -> None:
    shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
