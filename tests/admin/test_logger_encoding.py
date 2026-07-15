import io


def test_logger_console_sink_replaces_unencodable_characters():
    from core.logger import _safe_console_stream

    raw = io.BytesIO()
    original = io.TextIOWrapper(raw, encoding="gbk", errors="strict", line_buffering=True)
    stream = _safe_console_stream(original)

    stream.write("checkmark: \u2713\n")
    stream.flush()

    assert raw.getvalue().decode("gbk").replace("\r\n", "\n") == "checkmark: ?\n"
