#!/usr/bin/env python3
"""MANUAL Home Assistant check (NOT run by pytest).

Reads SERVER-side configuration and probes the HA HTTP API.
Run explicitly only:

    python scripts/check_home_assistant.py
    python scripts/check_home_assistant.py --states
    python scripts/check_home_assistant.py --url http://192.168.0.13:8123

The token is NEVER printed. Exit code is non-zero on any failure.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


async def _amain(url: str, timeout: float, show_states: bool) -> int:
    from core.config import get_settings
    from core.home_assistant.client import HomeAssistantClient, HomeAssistantError

    settings = get_settings()
    if not settings.home_assistant_enabled:
        print("Home Assistant configuration: DISABLED (JARVIS_HOME_ASSISTANT_ENABLED=false)")
        return 1
    if not url:
        print("Home Assistant configuration: FAIL (JARVIS_HOME_ASSISTANT_URL is empty)")
        return 1
    if not settings.home_assistant_token:
        print("Home Assistant configuration: FAIL (JARVIS_HOME_ASSISTANT_TOKEN is empty)")
        return 1
    print("Home Assistant configuration: OK")

    client = HomeAssistantClient(
        base_url=url,
        token=settings.home_assistant_token,
        timeout=timeout,
    )
    print(f"URL: {client.base_url}")

    try:
        health = await client.health()
    except HomeAssistantError as e:
        print(f"Authentication/API: FAIL ({e.kind}): {e.message}")
        return 1
    print("Authentication: OK")
    print("API: OK")

    version = health.get("version")
    print(f"Version: {version if version else '(not reported by this HA version)'}")

    if show_states:
        try:
            states = await client.get_states()
        except HomeAssistantError as e:
            print(f"States: FAIL ({e.kind}): {e.message}")
            return 1
        print(f"States: OK ({len(states)} entities)")
        for state in states[:10]:
            print(f"  - {state.get('entity_id')}: {state.get('state')}")

    return 0


def main() -> int:
    from core.config import get_settings

    settings = get_settings()
    parser = argparse.ArgumentParser(description="Manual Home Assistant check (real network).")
    parser.add_argument("--url", default=settings.home_assistant_url)
    parser.add_argument("--timeout", type=float, default=settings.home_assistant_timeout)
    parser.add_argument("--states", action="store_true", help="Also list entity states")
    args = parser.parse_args()
    return asyncio.run(_amain(args.url, args.timeout, args.states))


if __name__ == "__main__":
    raise SystemExit(main())
