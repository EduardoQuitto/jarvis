#!/usr/bin/env python3
"""MANUAL check for the CORE -> SERVER bridge (NOT run by pytest).

Real-network smoke test against the Ubuntu SERVER. Run explicitly only:

    python scripts/check_remote_server.py
    python scripts/check_remote_server.py --url http://192.168.0.13:8000 --api-key <key>
    python scripts/check_remote_server.py --message "hello via bridge"

Steps:
  1. GET /health
  2. GET /tools (shows name + visibility + security_level)
  3. POST /tools/execute echo (only if the SERVER advertises echo as SHARED)

Requires JARVIS_SERVER_URL + JARVIS_SERVER_API_KEY (via .env or flags).
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


async def _amain(url: str, api_key: str, timeout: float, message: str) -> int:
    from core.network.node_client import RemoteNodeClient, RemoteNodeError

    client = RemoteNodeClient(base_url=url, api_key=api_key, timeout=timeout)

    print(f"[1/3] GET {url}/health")
    try:
        health = await client.health()
    except RemoteNodeError as e:
        print(f"  FAIL ({e.kind}): {e.message}")
        return 1
    print(f"  OK: status={health.get('status')} node={health.get('node_id')} "
          f"role={health.get('node_role')} tools={health.get('registered_tools_count')}")

    print("[2/3] GET /tools")
    try:
        tools = await client.list_tools()
    except RemoteNodeError as e:
        print(f"  FAIL ({e.kind}): {e.message}")
        return 1
    for t in tools:
        print(f"  - {t.get('name')} visibility={t.get('visibility')} level={t.get('security_level')}")
    shared_names = {t.get("name") for t in tools if t.get("visibility") == "SHARED"}

    print("[3/3] POST /tools/execute echo")
    if "echo" not in shared_names:
        print("  SKIP: SERVER does not advertise 'echo' as SHARED.")
        return 0
    try:
        result = await client.execute_shared_tool("echo", {"message": message})
    except RemoteNodeError as e:
        print(f"  FAIL ({e.kind}): {e.message}")
        return 1
    print(f"  OK: success={result.get('success')} data={result.get('data')} "
          f"error={result.get('error')} level={result.get('security_level')}")
    return 0 if result.get("success") else 2


def main() -> int:
    from core.config import get_settings

    settings = get_settings()
    parser = argparse.ArgumentParser(description="Manual CORE -> SERVER bridge check (real network).")
    parser.add_argument("--url", default=settings.server_url or "http://192.168.0.13:8000")
    parser.add_argument("--api-key", default=settings.server_api_key or settings.api_key)
    parser.add_argument("--timeout", type=float, default=settings.server_timeout)
    parser.add_argument("--message", default="hello via bridge")
    args = parser.parse_args()
    if not args.url:
        print("Missing SERVER URL: set JARVIS_SERVER_URL or pass --url.")
        return 1
    return asyncio.run(_amain(args.url, args.api_key, args.timeout, args.message))


if __name__ == "__main__":
    raise SystemExit(main())
