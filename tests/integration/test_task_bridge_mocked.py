"""Mocked integration + E2E: CORE -> DistributedTaskClient -> RemoteNodeClient.

The SERVER task API is simulated in-memory with httpx.MockTransport
(zero real network, zero real database):

  POST /api/tasks/                -> create (PENDING)
  GET  /api/tasks/                -> list (status filter + limit)
  GET  /api/tasks/{id}            -> full payload or 404
  PATCH /api/tasks/{id}           -> apply status/result/progress; `error`
                                     appends to the `errors` history
  POST /api/tasks/{id}/{cancel,pause,resume} -> transition status
"""

import json

import httpx
import pytest

from core.config import reset_settings
from core.contracts.enums import TaskStatus
from core.network.node_client import RemoteNodeClient
from core.network.task_client import DistributedTaskClient


class _FakeTaskServer:
    """In-memory simulation of the SERVER task endpoints."""

    TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}

    def __init__(self):
        self.tasks = {}
        self._next_id = 0
        self.auth_headers = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.auth_headers.append(request.headers.get("authorization"))
        method, path = request.method, request.url.path
        body = json.loads(request.content.decode() or "{}") if request.content else {}

        if method == "POST" and path == "/api/tasks/":
            self._next_id += 1
            task_id = f"task-{self._next_id}"
            self.tasks[task_id] = {
                "task_id": task_id,
                "objective": body.get("objective", ""),
                "context": body.get("context", {}),
                "priority": body.get("priority", "normal"),
                "conversation_id": body.get("conversation_id"),
                "device_id": body.get("device_id"),
                "status": "PENDING",
                "progress_pct": 0.0,
                "result": None,
                "errors": [],
            }
            created = self.tasks[task_id]
            return httpx.Response(200, json={"task_id": task_id, "objective": created["objective"],
                                             "status": "PENDING", "created_at": ""})

        if method == "GET" and path == "/api/tasks/":
            status = request.url.params.get("status")
            limit = int(request.url.params.get("limit", 50))
            items = [t for t in self.tasks.values() if status is None or t["status"] == status]
            summaries = [{"task_id": t["task_id"], "objective": t["objective"],
                          "status": t["status"], "progress_pct": t["progress_pct"]} for t in items[:limit]]
            return httpx.Response(200, json=summaries)

        if path.startswith("/api/tasks/"):
            rest = path[len("/api/tasks/"):]
            task_id, _, action = rest.partition("/")
            task = self.tasks.get(task_id)
            if task is None:
                return httpx.Response(404, json={"detail": "Task not found"})
            if method == "GET" and not action:
                return httpx.Response(200, json=dict(task))
            if method == "PATCH" and not action:
                if "status" in body:
                    task["status"] = body["status"]
                if "result" in body:
                    task["result"] = body["result"]
                if "progress_pct" in body:
                    task["progress_pct"] = body["progress_pct"]
                if "error" in body:
                    task["errors"].append(body["error"])
                return httpx.Response(200, json={"status": "updated", "task_id": task_id})
            if method == "POST" and action in ("cancel", "pause", "resume"):
                task["status"] = {"cancel": "CANCELLED", "pause": "PENDING",
                                  "resume": "RUNNING"}[action]
                return httpx.Response(200, json={"status": action + "d", "task_id": task_id})

        return httpx.Response(404, json={"detail": "not found"})


@pytest.fixture
def task_bridge(monkeypatch):
    monkeypatch.setenv("JARVIS_SERVER_URL", "http://simulated-server:8000")
    monkeypatch.setenv("JARVIS_SERVER_API_KEY", "test-key")
    reset_settings()
    server = _FakeTaskServer()
    transport = httpx.MockTransport(server.handler)
    client = RemoteNodeClient(base_url="http://simulated-server:8000", api_key="test-key",
                              timeout=5.0, transport=transport)
    dtc = DistributedTaskClient(client=client, device_id="jarvis-core")
    return dtc, server


@pytest.mark.asyncio
async def test_core_to_server_task_roundtrip(task_bridge):
    dtc, server = task_bridge
    created = await dtc.create_task(objective="prepare report", conversation_id="sess-7")
    assert created.task_id.startswith("task-")
    assert created.status == TaskStatus.PENDING
    assert server.tasks[created.task_id]["device_id"] == "jarvis-core"
    assert server.tasks[created.task_id]["conversation_id"] == "sess-7"

    fetched = await dtc.get_task(created.task_id)
    assert fetched is not None and fetched.objective == "prepare report"

    listed = await dtc.list_tasks()
    assert [t.task_id for t in listed] == [created.task_id]


@pytest.mark.asyncio
async def test_e2e_create_progress_complete(task_bridge):
    dtc, _ = task_bridge
    created = await dtc.create_task(objective="e2e lifecycle")
    task_id = created.task_id

    assert (await dtc.get_task(task_id)).status == TaskStatus.PENDING

    progressed = await dtc.update_progress(task_id, 50.0)
    assert progressed.progress_pct == 50.0

    done = await dtc.complete_task(task_id, result="all good")
    assert done.status == TaskStatus.COMPLETED
    assert done.progress_pct == 100.0
    assert done.result == "all good"

    # Final read-back from the SERVER source of truth
    final = await dtc.get_task(task_id)
    assert final.status == TaskStatus.COMPLETED
    assert final.result == "all good"


@pytest.mark.asyncio
async def test_e2e_fail_preserves_errors_history(task_bridge):
    dtc, _ = task_bridge
    created = await dtc.create_task(objective="flaky job")
    failed = await dtc.fail_task(created.task_id, error="boom")
    assert failed.status == TaskStatus.FAILED
    assert failed.errors == ["boom"]


@pytest.mark.asyncio
async def test_e2e_cancel_pause_resume(task_bridge):
    dtc, _ = task_bridge
    created = await dtc.create_task(objective="controllable job")
    task_id = created.task_id

    assert (await dtc.pause_task(task_id)).status == TaskStatus.PENDING
    assert (await dtc.resume_task(task_id)).status == TaskStatus.RUNNING
    assert (await dtc.cancel_task(task_id)).status == TaskStatus.CANCELLED

    assert await dtc.get_task("task-does-not-exist") is None


@pytest.mark.asyncio
async def test_bearer_auth_on_every_call(task_bridge):
    dtc, server = task_bridge
    await dtc.create_task(objective="auth check")
    assert server.auth_headers and all(h == "Bearer test-key" for h in server.auth_headers)
