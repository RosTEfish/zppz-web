from __future__ import annotations

import signal
import subprocess
import sys
import time


children: list[subprocess.Popen] = []


def _stop(_signum, _frame) -> None:
    for child in children:
        if child.poll() is None:
            child.terminate()


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    children.extend(
        [
            subprocess.Popen([sys.executable, "-m", "app.worker"]),
            subprocess.Popen([sys.executable, "-m", "app.webhook_worker"]),
        ]
    )
    while True:
        for child in children:
            status = child.poll()
            if status is not None:
                _stop(signal.SIGTERM, None)
                for sibling in children:
                    if sibling is not child:
                        sibling.wait(timeout=30)
                return int(status)
        time.sleep(0.2)


if __name__ == "__main__":
    raise SystemExit(main())
