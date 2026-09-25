from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient

FINISHED = {"complete", "failed", "cancelled", "interrupted"}


def wait_for(client: TestClient, task: dict[str, Any], timeout: float = 300.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = client.get(f"/api/tasks/{task['id']}").json()["task"]
        if state["status"] in FINISHED:
            return state
        time.sleep(0.1)
    raise AssertionError(f"Task {task['id']} did not finish in {timeout} s")
