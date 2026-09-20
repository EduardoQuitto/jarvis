"""Unit tests for the Task Bridge (RemoteNodeClient task methods + DistributedTaskClient).

No test here touches the real Ubuntu SERVER — HTTP is simulated via
httpx.MockTransport. Router-level tests use the real FastAPI app against
an isolated temporary database (see conftest).
"""

import json

import httpx
import pytest

from core.config import reset_settings
from core.contracts.enums import TaskStatus
from core.network.node_client import RemoteNodeClient, RemoteNodeError
from core.network.task_client import DistributedTaskClient, dict_to_task


def _make_client(handler, base_url="http://testserver", api_key="test-key", timeout=5.0):
    transport = httpx.MockTransport(handler)
    return RemoteNodeClient(base_url=base_url, api_key=api_key, timeout=timeout, transport=transport)


def _make_task_client(handler, device_id="jarvis-core"):
    return DistributedTaskClient(client=_make_client(handler), device_id=device_id)


# --- RemoteNodeClient: task methods, success paths ---

@pytest.mark.asyncio
async def test_create_task_posts_expected_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/tasks/"
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"task_id": "task-1", "objective": "do thing",
                                         "status": "PENDING", "created_at": ""})

    client = _make_client(handler)
    result = await client.create_task(objective="do thing", context={"a": 1},
                                      priority="high", conversation_id="sess-1",
                                      device_id="jarvis-core")
    assert result["task_id"] == "task-1"
    assert seen["auth"] == "Bearer test-key"
    body = seen["body"]
    assert body["objective"] == "do thing"
    assert body["context"] == {"a": 1}
    assert body["priority"] == "high"
    assert body["conversation_id"] == "sess-1"
    assert body["device_id"] == "jarvis-core"


@pytest.mark.asyncio
async def test_list_tasks_sends_query_params():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/tasks/"
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=[{"task_id": "task-1", "objective": "x",
                                          "status": "PENDING", "progress_pct": 0.0}])

    client = _make_client(handler)
    tasks = await client.list_tasks(status="PENDING", limit=10)
    assert len(tasks) == 1
    assert seen["params"] == {"limit": "10", "status": "PENDING"}


@pytest.mark.asyncio
async def test_get_task_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tasks/task-1"
        return httpx.Response(200, json={"task_id": "task-1", "objective": "x",
                                         "status": "RUNNING", "progress_pct": 50.0,
                                         "result": None, "errors": []})

    client = _make_client(handler)
    assert (await client.get_task("task-1"))["status"] == "RUNNING"


@pytest.mark.asyncio
async def test_update_task_sends_only_set_fields():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        assert request.url.path == "/api/tasks/task-1"
        seen["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"status": "updated", "task_id": "task-1"})

    client = _make_client(handler)
    await client.update_task("task-1", progress_pct=50.0)
    assert seen["body"] == {"progress_pct": 50.0}

    await client.update_task("task-1", status="COMPLETED", result="done", progress_pct=100.0)
    assert seen["body"] == {"status": "COMPLETED", "result": "done", "progress_pct": 100.0}

    await client.update_task("task-1", status="FAILED", error="boom")
    assert seen["body"] == {"status": "FAILED", "error": "boom"}


@pytest.mark.asyncio
async def test_cancel_pause_resume_hit_expected_paths():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        seen.append(request.url.path)
        action = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json={"status": action + "d", "task_id": "task-1"})

    client = _make_client(handler)
    await client.cancel_task("task-1")
    await client.pause_task("task-1")
    await client.resume_task("task-1")
    assert seen == ["/api/tasks/task-1/cancel", "/api/tasks/task-1/pause", "/api/tasks/task-1/resume"]


# --- RemoteNodeClient: task methods, failure paths ---

@pytest.mark.asyncio
async def test_task_auth_failure_is_standardized():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "forbidden"})

    client = _make_client(handler)
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.get_task("task-1")
    assert exc_info.value.kind == "auth"
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_task_timeout_is_standardized():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = _make_client(handler)
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.create_task(objective="x")
    assert exc_info.value.kind == "timeout"


@pytest.mark.asyncio
async def test_task_connection_failure_is_standardized():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = _make_client(handler)
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.list_tasks()
    assert exc_info.value.kind == "connection"


@pytest.mark.asyncio
async def test_task_invalid_response_is_standardized():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json{{{", headers={"Content-Type": "application/json"})

    client = _make_client(handler)
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.get_task("task-1")
    assert exc_info.value.kind == "invalid_response"


@pytest.mark.asyncio
async def test_task_4xx_is_client_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Task not found"})

    client = _make_client(handler)
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.get_task("missing")
    assert exc_info.value.kind == "client_error"
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_task_5xx_is_server_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    client = _make_client(handler)
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.cancel_task("task-1")
    assert exc_info.value.kind == "server_error"
    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_task_empty_identifiers_rejected_locally():
    client = _make_client(lambda request: httpx.Response(200, json={}))
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.create_task(objective="")
    assert exc_info.value.kind == "client_error"
    with pytest.raises(RemoteNodeError) as exc_info:
        await client.get_task("")
    assert exc_info.value.kind == "client_error"


# --- DistributedTaskClient ---

def _task_dict(task_id="task-1", status="PENDING", **overrides):
    payload = {"task_id": task_id, "objective": "do thing", "status": status,
               "progress_pct": 0.0, "result": None, "errors": []}
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_distributed_create_task_attributes_core_and_returns_contract():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/tasks/":
            seen["body"] = json.loads(request.content.decode())
            return httpx.Response(200, json={"task_id": "task-9", "objective": "do thing",
                                             "status": "PENDING", "created_at": ""})
        if request.method == "GET" and request.url.path == "/api/tasks/task-9":
            return httpx.Response(200, json=_task_dict("task-9", device_id="jarvis-core"))
        return httpx.Response(404, json={"detail": "not found"})

    dtc = _make_task_client(handler)
    task = await dtc.create_task(objective="do thing", conversation_id="sess-1")
    assert seen["body"]["device_id"] == "jarvis-core"
    assert seen["body"]["conversation_id"] == "sess-1"
    assert task.task_id == "task-9"
    assert task.status == TaskStatus.PENDING
    assert task.device_id == "jarvis-core"


@pytest.mark.asyncio
async def test_distributed_get_task_missing_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Task not found"})

    dtc = _make_task_client(handler)
    assert await dtc.get_task("missing") is None


@pytest.mark.asyncio
async def test_distributed_get_task_propagates_non_404_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    dtc = _make_task_client(handler)
    with pytest.raises(RemoteNodeError) as exc_info:
        await dtc.get_task("task-1")
    assert exc_info.value.kind == "server_error"


@pytest.mark.asyncio
async def test_distributed_complete_task_lifecycle_fields():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PATCH":
            seen["body"] = json.loads(request.content.decode())
            return httpx.Response(200, json={"status": "updated", "task_id": "task-1"})
        return httpx.Response(200, json=_task_dict("task-1", status="COMPLETED",
                                                   progress_pct=100.0, result="done"))

    dtc = _make_task_client(handler)
    task = await dtc.complete_task("task-1", result="done")
    assert seen["body"] == {"status": "COMPLETED", "result": "done", "progress_pct": 100.0}
    assert task.status == TaskStatus.COMPLETED
    assert task.progress_pct == 100.0
    assert task.result == "done"


@pytest.mark.asyncio
async def test_distributed_fail_task_preserves_errors_semantics():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PATCH":
            seen["body"] = json.loads(request.content.decode())
            return httpx.Response(200, json={"status": "updated", "task_id": "task-1"})
        return httpx.Response(200, json=_task_dict("task-1", status="FAILED", errors=["boom"]))

    dtc = _make_task_client(handler)
    task = await dtc.fail_task("task-1", error="boom")
    # `error` travels only as an API field; the SERVER router translates it
    # into the `errors` history (there is no singular `error` column).
    assert seen["body"] == {"status": "FAILED", "error": "boom"}
    assert task.status == TaskStatus.FAILED
    assert task.errors == ["boom"]


@pytest.mark.asyncio
async def test_distributed_progress_and_actions():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json=_task_dict("task-1", status="RUNNING", progress_pct=50.0))
        if request.method == "PATCH":
            return httpx.Response(200, json={"status": "updated", "task_id": "task-1"})
        status_word = {"cancel": "cancelled", "pause": "paused", "resume": "resumed"}[request.url.path.rsplit("/", 1)[-1]]
        return httpx.Response(200, json={"status": status_word, "task_id": "task-1"})

    dtc = _make_task_client(handler)
    task = await dtc.update_progress("task-1", 50.0)
    assert task.progress_pct == 50.0
    await dtc.cancel_task("task-1")
    await dtc.pause_task("task-1")
    await dtc.resume_task("task-1")
    assert ("PATCH", "/api/tasks/task-1") in calls
    assert ("POST", "/api/tasks/task-1/cancel") in calls
    assert ("POST", "/api/tasks/task-1/pause") in calls
    assert ("POST", "/api/tasks/task-1/resume") in calls


@pytest.mark.asyncio
async def test_distributed_from_settings_none_when_unconfigured(monkeypatch):
    monkeypatch.setenv("JARVIS_SERVER_URL", "")
    reset_settings()
    assert DistributedTaskClient.from_settings() is None


def test_dict_to_task_defaults_and_unknown_status():
    task = dict_to_task({"task_id": "t", "objective": "o", "status": "WEIRD"})
    assert task.status == TaskStatus.PENDING
    assert task.errors == []
    assert task.progress_pct == 0.0


# --- Router error/errors semantics (real app, isolated tmp DB) ---

@pytest.mark.asyncio
async def test_router_patch_error_appends_to_errors_history():
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app
    from core.config import get_settings

    app = create_app()
    headers = {"Authorization": f"Bearer {get_settings().api_key}"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = (await client.post("/api/tasks/", json={"objective": "router error test"},
                                     headers=headers)).json()
        task_id = created["task_id"]

        r1 = await client.patch(f"/api/tasks/{task_id}", json={"error": "first boom"}, headers=headers)
        assert r1.status_code == 200
        r2 = await client.patch(f"/api/tasks/{task_id}", json={"error": "second boom"}, headers=headers)
        assert r2.status_code == 200

        fetched = (await client.get(f"/api/tasks/{task_id}", headers=headers)).json()
        assert fetched["errors"] == ["first boom", "second boom"]


@pytest.mark.asyncio
async def test_router_create_accepts_conversation_id():
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app
    from core.config import get_settings
    from core.task.manager import TaskManager

    app = create_app()
    headers = {"Authorization": f"Bearer {get_settings().api_key}"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = (await client.post("/api/tasks/", json={"objective": "conv test",
                                                           "conversation_id": "sess-42",
                                                           "device_id": "jarvis-core"},
                                     headers=headers)).json()
        assert "task_id" in created

        stored = await TaskManager().get_task(created["task_id"])
        assert stored is not None
        assert stored.conversation_id == "sess-42"
        assert stored.device_id == "jarvis-core"
