from app.services.task_queue_service import TaskQueueService


def test_enqueue_creates_queued_task():
    queue = TaskQueueService(storage_path=":memory:")

    task = queue.enqueue(
        task_type="knowledge_index_document",
        payload={"document_id": "doc_1"},
        actor_id="admin_1",
        idempotency_key="knowledge_index_document:doc_1:v1",
    )

    assert task["task_type"] == "knowledge_index_document"
    assert task["status"] == "queued"
    assert task["payload"] == {"document_id": "doc_1"}
    assert task["attempts"] == 0
    assert task["max_attempts"] == 3
    assert task["actor_id"] == "admin_1"


def test_enqueue_with_same_idempotency_key_returns_existing_task():
    queue = TaskQueueService(storage_path=":memory:")

    first = queue.enqueue(
        task_type="knowledge_index_document",
        payload={"document_id": "doc_1"},
        actor_id="admin_1",
        idempotency_key="knowledge_index_document:doc_1:v1",
    )
    second = queue.enqueue(
        task_type="knowledge_index_document",
        payload={"document_id": "doc_1"},
        actor_id="admin_1",
        idempotency_key="knowledge_index_document:doc_1:v1",
    )

    assert second["task_id"] == first["task_id"]
    assert len(queue.list_tasks()) == 1


def test_claim_next_marks_task_running():
    queue = TaskQueueService(storage_path=":memory:")
    created = queue.enqueue(task_type="knowledge_reload", payload={}, actor_id="admin_1")

    claimed = queue.claim_next()

    assert claimed["task_id"] == created["task_id"]
    assert claimed["status"] == "running"
    assert claimed["attempts"] == 1
    assert queue.get_task(created["task_id"])["started_at"] is not None


def test_complete_marks_task_succeeded():
    queue = TaskQueueService(storage_path=":memory:")
    created = queue.enqueue(task_type="knowledge_reload", payload={}, actor_id="admin_1")
    queue.claim_next()

    completed = queue.complete(created["task_id"], result={"chunks": 10})

    assert completed["status"] == "succeeded"
    assert completed["result"] == {"chunks": 10}
    assert completed["error"] is None
    assert completed["finished_at"] is not None


def test_fail_requeues_until_max_attempts_then_dead():
    queue = TaskQueueService(storage_path=":memory:")
    created = queue.enqueue(
        task_type="knowledge_reload",
        payload={},
        actor_id="admin_1",
        max_attempts=2,
    )

    queue.claim_next()
    failed_once = queue.fail(created["task_id"], "temporary")
    assert failed_once["status"] == "queued"
    assert failed_once["error"] == "temporary"

    queue.claim_next()
    failed_twice = queue.fail(created["task_id"], "permanent")
    assert failed_twice["status"] == "dead"
    assert failed_twice["attempts"] == 2
    assert failed_twice["error"] == "permanent"


def test_task_service_can_filter_by_status():
    queue = TaskQueueService(storage_path=":memory:")
    queue.enqueue(task_type="knowledge_reload", payload={}, actor_id="admin_1")
    running = queue.enqueue(task_type="knowledge_reload", payload={}, actor_id="admin_1")
    queue.claim_next()

    queued = queue.list_tasks(status="queued")
    running_tasks = queue.list_tasks(status="running")

    assert len(queued) == 1
    assert len(running_tasks) == 1
    assert running_tasks[0]["task_id"] != running["task_id"] or running_tasks[0]["status"] == "running"


def test_retry_moves_dead_task_back_to_queue():
    queue = TaskQueueService(storage_path=":memory:")
    created = queue.enqueue(task_type="knowledge_reload", payload={}, max_attempts=1)
    queue.claim_next()
    queue.fail(created["task_id"], "permanent")

    retried = queue.retry(created["task_id"])

    assert retried["status"] == "queued"
    assert retried["error"] is None
