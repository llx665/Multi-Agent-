"""Chroma telemetry compatibility helpers."""

from __future__ import annotations


def disable_chroma_telemetry() -> None:
    """Disable Chroma's PostHog telemetry path.

    Chroma 0.6.1 calls the older posthog.capture(user_id, event, properties)
    signature. Newer posthog releases expose an incompatible capture API, so
    Chroma logs noisy telemetry failures even when anonymized telemetry is off.
    """
    try:
        import chromadb.telemetry.product.posthog as chroma_posthog
    except Exception:
        return

    try:
        chroma_posthog.posthog.disabled = True
    except Exception:
        pass

    def _disabled_direct_capture(self, event):
        del self, event
        return None

    chroma_posthog.Posthog._direct_capture = _disabled_direct_capture
