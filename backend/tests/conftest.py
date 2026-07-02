import atexit
import os
from pathlib import Path
import shutil
import tempfile


TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="zppz-tests-"))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DATA_DIR"] = str(TEST_DATA_DIR)
os.environ["ADMIN_SEED_PASSWORD"] = "change-me-please"


@atexit.register
def cleanup_test_data() -> None:
    shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
