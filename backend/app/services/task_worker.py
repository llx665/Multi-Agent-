from __future__ import annotations

import time
from typing import Callable, Dict, Optional

from app.services.task_queue_service import TaskQueueService, task_queue_service


TaskHandler = Callable[[dict], dict]


class TaskWorker:
    def __init__(
        self,
        queue: TaskQueueService = task_queue_service,
        handlers: Optional[Dict[str, TaskHandler]] = None,
    ) -> None:
        self.queue = queue
        self.handlers = handlers or {}

    def run_once(self) -> bool:
        task = self.queue.claim_next(task_types=list(self.handlers.keys()))
        if task is None:
            return False

        handler = self.handlers.get(task["task_type"])
        if handler is None:
            self.queue.fail(task["task_id"], f"no handler for {task['task_type']}")
            return True

        try:
            result = handler(task["payload"])
            self.queue.complete(task["task_id"], result=result)
        except Exception as exc:
            self.queue.fail(task["task_id"], str(exc))
        return True

    def run_forever(self, *, idle_sleep_seconds: float = 1.0) -> None:
        while True:
            did_work = self.run_once()
            if not did_work:
                time.sleep(idle_sleep_seconds)
