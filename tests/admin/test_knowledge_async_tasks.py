from app.services.task_queue_service import TaskQueueService
from app.services.task_worker import TaskWorker


def test_worker_dispatches_claimed_task_to_handler():
    queue = TaskQueueService(storage_path=":memory:")
    seen = []

    def handler(payload):
        seen.append(payload)
        return {"indexed": payload["document_id"]}

    worker = TaskWorker(queue, handlers={"knowledge_index_document": handler})
    task = queue.enqueue(
        task_type="knowledge_index_document",
        payload={"document_id": "doc_1"},
        actor_id="admin_1",
    )

    assert worker.run_once() is True
    assert seen == [{"document_id": "doc_1"}]
    stored = queue.get_task(task["task_id"])
    assert stored["status"] == "succeeded"
    assert stored["result"] == {"indexed": "doc_1"}


def test_enqueue_document_index_returns_task(monkeypatch):
    from app.services import knowledge_admin_service as module

    queue = TaskQueueService(storage_path=":memory:")
    monkeypatch.setattr(module, "task_queue_service", queue, raising=False)

    task = module.knowledge_admin_service.enqueue_document_index(
        document_id="doc_1",
        version_id="ver_1",
        actor_id="admin_1",
    )

    assert task["status"] == "queued"
    assert task["task_type"] == "knowledge_index_document"
    assert task["payload"] == {"document_id": "doc_1", "version_id": "ver_1"}


def test_enqueue_reload_returns_task(monkeypatch):
    from app.services import knowledge_admin_service as module

    queue = TaskQueueService(storage_path=":memory:")
    monkeypatch.setattr(module, "task_queue_service", queue, raising=False)

    task = module.knowledge_admin_service.enqueue_reload(actor_id="admin_1")

    assert task["status"] == "queued"
    assert task["task_type"] == "knowledge_reload"
    assert task["payload"] == {}


def test_async_reload_response_shape(monkeypatch):
    from app.services import knowledge_admin_service as module

    queue = TaskQueueService(storage_path=":memory:")
    monkeypatch.setattr(module, "task_queue_service", queue, raising=False)

    task = module.knowledge_admin_service.enqueue_reload(actor_id="admin_1")
    response = {
        "success": True,
        "task_id": task["task_id"],
        "status": task["status"],
        "message": "knowledge reload queued",
    }

    assert response["status"] == "queued"
    assert response["task_id"].startswith("task_")
