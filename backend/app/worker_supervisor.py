from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


SUBMISSION_WORKER_COUNT = 2
children: list[subprocess.Popen] = []


def _submission_worker_env(index: int) -> dict[str, str]:
    env = os.environ.copy()
    # Only the first process expires upload intents, so two workers cannot
    # insert the same storage-deletion row.
    env["SUBMISSION_WORKER_CLEANUP"] = "1" if index == 0 else "0"
    return env


def _stop(_signum, _frame) -> None:
    for child in children:
        if child.poll() is None:
            child.terminate()


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    children.extend(
        subprocess.Popen(
            [sys.executable, "-m", "app.worker"],
            env=_submission_worker_env(index),
        )
        for index in range(SUBMISSION_WORKER_COUNT)
    )
    children.append(subprocess.Popen([sys.executable, "-m", "app.webhook_worker"]))
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
