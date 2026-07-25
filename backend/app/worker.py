from __future__ import annotations

import logging
import signal
import time

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


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    logger.info("submission worker started")
    next_cleanup = 0.0
    while not _stopping:
        now = time.monotonic()
        if now >= next_cleanup:
            cleanup_expired_upload_intents()
            next_cleanup = now + 60
        if not process_next_job():
            time.sleep(2)
    logger.info("submission worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
