def test_disable_chroma_telemetry_patches_incompatible_posthog_capture(monkeypatch):
    import sys
    import types

    chromadb = types.ModuleType("chromadb")
    telemetry = types.ModuleType("chromadb.telemetry")
    product = types.ModuleType("chromadb.telemetry.product")
    chroma_posthog = types.ModuleType("chromadb.telemetry.product.posthog")

    class Posthog:
        def _direct_capture(self, event):
            del self, event
            return None

    chroma_posthog.Posthog = Posthog
    chroma_posthog.posthog = types.SimpleNamespace(disabled=False)

    monkeypatch.setitem(sys.modules, "chromadb", chromadb)
    monkeypatch.setitem(sys.modules, "chromadb.telemetry", telemetry)
    monkeypatch.setitem(sys.modules, "chromadb.telemetry.product", product)
    monkeypatch.setitem(sys.modules, "chromadb.telemetry.product.posthog", chroma_posthog)

    from tools.rag.chroma_telemetry import disable_chroma_telemetry

    calls = []

    def noisy_direct_capture(self, event):
        calls.append((self, event))
        raise TypeError("capture() takes 1 positional argument but 3 were given")

    monkeypatch.setattr(chroma_posthog.Posthog, "_direct_capture", noisy_direct_capture)

    disable_chroma_telemetry()

    chroma_posthog.Posthog._direct_capture(object(), object())

    assert calls == []
    assert chroma_posthog.posthog.disabled is True
