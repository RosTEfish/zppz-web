from __future__ import annotations

import logging
import signal
import time

from app.core.config import get_settings
from app.core.observability import init_error_tracking
from app.modules.realtime.outbox import prune_domain_events_if_due
from app.modules.webhooks.service import cleanup_expired_assets, materialize_publication_events, process_next_delivery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
_stopping = False


def _stop(_signum, _frame) -> None:
    global _stopping
    _stopping = True


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    init_error_tracking(capture_logged_errors=True)
    logger.info("webhook worker started")
    next_scan = 0.0
    next_cleanup = 0.0
    while not _stopping:
        now = time.monotonic()
        if now >= next_scan:
            materialize_publication_events()
            next_scan = now + get_settings().webhook_scan_interval_seconds
        if now >= next_cleanup:
            cleanup_expired_assets()
            # The webhook worker does not itself change pages the SSE stream watches
            # (it writes the outbound publication outbox). The shared Session hook
            # still publishes if a future change touches those tables, and this
            # prune keeps domain_events bounded if the API process is down.
            prune_domain_events_if_due()
            next_cleanup = now + 3600
        if not process_next_delivery():
            time.sleep(0.25)
    logger.info("webhook worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
