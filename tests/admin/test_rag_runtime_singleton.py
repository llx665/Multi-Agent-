import sys
from types import SimpleNamespace


def test_get_rag_tool_reuses_module_level_singleton(monkeypatch):
    from app.services import rag_runtime

    sentinel = object()

    class UnexpectedRAGTool:
        def __init__(self):
            raise AssertionError("get_rag_tool should not create a second RAGTool instance")

    fake_module = SimpleNamespace(rag_tool=sentinel, RAGTool=UnexpectedRAGTool)
    monkeypatch.setitem(sys.modules, "tools.rag_tool", fake_module)
    monkeypatch.setattr(rag_runtime, "_rag_tool_instance", None)

    assert rag_runtime.get_rag_tool() is sentinel
    assert rag_runtime.get_loaded_rag_tool() is sentinel
