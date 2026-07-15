"""Launch both user-facing and admin FastAPI backends together."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent


def start_server(target: str, port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(BACKEND_ROOT), str(PROJECT_ROOT), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)

    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            target,
            "--reload",
            "--reload-dir",
            str(PROJECT_ROOT),
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
        ],
        cwd=str(BACKEND_ROOT),
        env=env,
    )


def stop_server(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def main() -> int:
    user_backend = start_server("app.main:app", 8000)
    admin_backend = start_server("app.admin_main:app", 8001)
    processes = [user_backend, admin_backend]

    def shutdown(*_: object) -> None:
        for process in processes:
            stop_server(process)
        raise SystemExit(0)

    if os.name == "nt":
        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)
    else:
        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

    print("user backend:  http://localhost:8000")
    print("admin backend: http://localhost:8001")

    try:
        while True:
            for process in processes:
                return_code = process.poll()
                if return_code is not None:
                    for other in processes:
                        if other is not process:
                            stop_server(other)
                    return return_code
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
