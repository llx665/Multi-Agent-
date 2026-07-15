from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.task_handlers import TASK_HANDLERS
from app.services.task_queue_service import task_queue_service
from app.services.task_worker import TaskWorker


def main() -> None:
    parser = argparse.ArgumentParser(description="Run async task worker.")
    parser.add_argument("--once", action="store_true", help="Process one task and exit.")
    args = parser.parse_args()

    worker = TaskWorker(task_queue_service, handlers=TASK_HANDLERS)
    if args.once:
        worker.run_once()
        return
    worker.run_forever()


if __name__ == "__main__":
    main()
