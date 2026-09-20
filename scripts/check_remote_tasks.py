#!/usr/bin/env python3
"""MANUAL check for the Task Bridge lifecycle (NOT run by pytest).

Real-network smoke test against the Ubuntu SERVER. Run explicitly only:

    python scripts/check_remote_tasks.py
    python scripts/check_remote_tasks.py --url http://192.168.0.13:8000 --api-key <key>
    python scripts/check_remote_tasks.py --objective "Manual bridge check"

Flow:
  1. POST /api/tasks/              (create, device_id=jarvis-core)
  2. GET  /api/tasks/{id}          (read back)
  3. PATCH /api/tasks/{id}         (progress 50%)
  4. PATCH /api/tasks/{id}         (complete with result)
  5. GET  /api/tasks/{id}          (final state)

Requires JARVIS_SERVER_URL + JARVIS_SERVER_API_KEY (via .env or flags).
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


async def _amain(url: str, api_key: str, timeout: float, objective: str) -> int:
    from core.network.node_client import RemoteNodeClient, RemoteNodeError

    client = RemoteNodeClient(base_url=url, api_key=api_key, timeout=timeout)

    print(f"[1/5] POST {url}/api/tasks/ (create)")
    try:
        created = await client.create_task(objective=objective, device_id="jarvis-core")
    except RemoteNodeError as e:
        print(f"  FAIL ({e.kind}): {e.message}")
        return 1
    task_id = created.get("task_id")
    print(f"  OK: task_id={task_id} status={created.get('status')}")
    if not task_id:
        print("  FAIL: SERVER did not return a task_id.")
        return 1

    print("[2/5] GET /api/tasks/{id}")
    try:
        fetched = await client.get_task(task_id)
    except RemoteNodeError as e:
        print(f"  FAIL ({e.kind}): {e.message}")
        return 1
    print(f"  OK: status={fetched.get('status')} progress={fetched.get('progress_pct')}")

    print("[3/5] PATCH progress=50%")
    try:
        await client.update_task(task_id, progress_pct=50.0)
    except RemoteNodeError as e:
        print(f"  FAIL ({e.kind}): {e.message}")
        return 1
    print("  OK")

    print("[4/5] PATCH complete with result")
    try:
        await client.update_task(task_id, status="COMPLETED", result="manual bridge check ok",
                                 progress_pct=100.0)
    except RemoteNodeError as e:
        print(f"  FAIL ({e.kind}): {e.message}")
        return 1
    print("  OK")

    print("[5/5] GET final state")
    try:
        final = await client.get_task(task_id)
    except RemoteNodeError as e:
        print(f"  FAIL ({e.kind}): {e.message}")
        return 1
    ok = final.get("status") == "COMPLETED" and float(final.get("progress_pct") or 0) == 100.0
    print(f"  OK: status={final.get('status')} progress={final.get('progress_pct')} "
          f"result={final.get('result')}")
    return 0 if ok else 2


def main() -> int:
    from core.config import get_settings

    settings = get_settings()
    parser = argparse.ArgumentParser(description="Manual Task Bridge lifecycle check (real network).")
    parser.add_argument("--url", default=settings.server_url or "http://192.168.0.13:8000")
    parser.add_argument("--api-key", default=settings.server_api_key or settings.api_key)
    parser.add_argument("--timeout", type=float, default=settings.server_timeout)
    parser.add_argument("--objective", default="Manual Task Bridge check (CORE -> SERVER)")
    args = parser.parse_args()
    if not args.url:
        print("Missing SERVER URL: set JARVIS_SERVER_URL or pass --url.")
        return 1
    return asyncio.run(_amain(args.url, args.api_key, args.timeout, args.objective))


if __name__ == "__main__":
    raise SystemExit(main())
