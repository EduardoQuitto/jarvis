#!/usr/bin/env python3
"""MANUAL fallback check: Ollama (forced down) -> Google Gemini -> Mock (NOT run by pytest).

Validates the REAL IntelligenceRouter fallback chain without touching the
installed Ollama on Windows: the script builds an OllamaProvider pointed at
a deliberately unavailable local port (fast connection refused), while
Google uses the real JARVIS_GOOGLE_* settings from .env.

Run explicitly only:

    .\\.venv\\Scripts\\python.exe scripts/check_llm_fallback.py

Expected outcome when the Google key is valid:
  1st provider tried : ollama  -> error (unreachable, simulated)
  2nd provider tried : google  -> valid answer, mock never called.

Nothing is printed that could leak the API key, and no persistent
configuration is modified.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

PROMPT = "Responda exatamente: FALLBACK GOOGLE OK"

# Deliberately unavailable endpoint: connection refused immediately, so the
# real Ollama installation is never touched and the test stays fast.
DEAD_OLLAMA_URL = "http://127.0.0.1:9"


async def _amain() -> int:
    from core.config import get_settings
    from core.contracts.llm import LLMMessage
    from core.events.bus import get_event_bus
    from core.events.models import EventType
    from core.llm.provider import OllamaProvider
    from core.llm.external_provider import ExternalProvider
    from core.llm.mock_provider import MockLLMProvider
    from core.llm.registry import ProviderRegistry
    from core.llm.router import IntelligenceRouter

    settings = get_settings()
    if not settings.google_api_key or not settings.google_base_url:
        print("Missing Google config: set JARVIS_GOOGLE_API_KEY / JARVIS_GOOGLE_BASE_URL.")
        return 1

    # 1. Ollama pointed at a dead port (simulated outage, real Ollama untouched).
    ollama = OllamaProvider(base_url=DEAD_OLLAMA_URL, model=settings.llm_model, timeout=5.0)
    # 2. Google with the real .env settings.
    google = ExternalProvider(
        base_url=settings.google_base_url,
        model=settings.google_model,
        api_key=settings.google_api_key,
        provider_name="google",
    )
    mock = MockLLMProvider()

    # 3. Registry mirroring create_router(): ollama(10, local) -> google(7) -> mock(1).
    registry = ProviderRegistry()
    registry.register(name="ollama", provider=ollama, priority=10.0,
                      capabilities=["text_generation"])
    registry.register(name="google", provider=google, priority=7.0,
                      capabilities=["text_generation"], cost_weight=0.5, local=False)
    registry.register(name="mock", provider=mock, priority=1.0,
                      capabilities=["text_generation"])
    router = IntelligenceRouter(registry=registry)

    # Track the real attempt order via router events.
    attempts = []

    async def _on_selected(event):
        attempts.append(("selected", event.data.get("provider"), event.data.get("model", "")))

    async def _on_failed(event):
        attempts.append(("failed", event.data.get("provider"), event.data.get("error", "")))

    bus = get_event_bus()
    bus.subscribe(EventType.PROVIDER_SELECTED, _on_selected)
    bus.subscribe(EventType.PROVIDER_FAILED, _on_failed)

    print(f"[setup] chain: ollama(10,local) -> google(7) -> mock(1) | prompt={PROMPT!r}")

    # Step 0: prove the simulated Ollama outage directly (fast: refused port).
    # The router itself filters unhealthy providers silently via health_check,
    # so this probe makes the Ollama failure visible in the report.
    print("[step 0] direct Ollama probe (simulated outage) ...")
    probe = await ollama.generate(messages=[LLMMessage(role="user", content="ping")])
    print(f"  ollama healthy   : {await ollama.health_check()}")
    print(f"  ollama error     : {str(probe.error_msg)[:160]}")

    response = await router.route(messages=[LLMMessage(role="user", content=PROMPT)],
                                  temperature=0.2, max_tokens=100)

    print("--- attempt order (from router events) ---")
    for kind, provider, detail in attempts:
        safe_detail = detail if kind == "selected" else str(detail)[:160]
        print(f"  {kind:8s} provider={provider} detail={safe_detail}")

    tried = [p for k, p, _ in attempts if k == "selected"]
    # NOTE: the router pre-filters unhealthy providers via health_check, so a
    # dead Ollama never appears as "selected" — the step-0 probe above is its
    # evidence. The first provider the router actually attempted is below.
    print(f"1st provider attempted by router: {tried[0] if tried else '?'}")
    for kind, provider, detail in attempts:
        if kind == "failed":
            print(f"provider failed    : {provider} error={str(detail)[:160]}")
    print(f"2nd provider attempted by router: {tried[1] if len(tried) > 1 else '(not reached)'},")

    if response.error_msg:
        print(f"Google response    : FAIL error={response.error_msg}")
        return 1
    print(f"Google response    : OK content={response.content!r}")
    print(f"final provider/model: {response.model!r}")
    mock_used = "mock" in tried
    print(f"mock called        : {mock_used} (expected False when Google answers)")
    if mock_used:
        print("NOTE: Google did not answer; the chain fell through to mock.")
        return 2
    return 0


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
