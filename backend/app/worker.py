from __future__ import annotations

import logging
import os
import signal
import time

from app.core.metrics import emit_contest_signals
from app.core.observability import init_error_tracking
from app.modules.realtime.outbox import prune_domain_events_if_due
from app.modules.submissions.processing import cleanup_expired_upload_intents, process_next_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)
_stopping = False


def _stop(_signum, _frame) -> None:
    global _stopping
    _stopping = True


def _cleanup_enabled() -> bool:
    return os.getenv("SUBMISSION_WORKER_CLEANUP", "1") != "0"


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    init_error_tracking(capture_logged_errors=True)
    cleanup_enabled = _cleanup_enabled()
    logger.info("submission worker started (cleanup %s)", "enabled" if cleanup_enabled else "disabled")
    next_cleanup = 0.0
    while not _stopping:
        now = time.monotonic()
        if cleanup_enabled and now >= next_cleanup:
            try:
                emit_contest_signals()
            except Exception:
                logger.exception("contest signal snapshot failed")
            prune_domain_events_if_due()
            cleanup_expired_upload_intents()
            next_cleanup = now + 60
        if not process_next_job():
            time.sleep(2)
    logger.info("submission worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
