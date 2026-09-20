#!/usr/bin/env python3
"""MANUAL check for the Google AI Studio (Gemini) cloud slot (NOT run by pytest).

Real-network smoke test against the Google OpenAI-compatible endpoint.
Run explicitly only:

    python scripts/check_google_provider.py
    python scripts/check_google_provider.py --model gemini-3.7-flash

Steps:
  1. Load settings, verify JARVIS_GOOGLE_API_KEY exists (never printed).
  2. Build the Google ExternalProvider (provider_name="google").
  3. health_check() -> GET {base_url}/models
  4. Simple non-streaming generation (no tools, no streaming yet).

Requires JARVIS_GOOGLE_API_KEY (via .env or environment).
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


async def _amain(api_key: str, base_url: str, model: str, timeout: float, prompt: str) -> int:
    from core.llm.external_provider import ExternalProvider
    from core.contracts.llm import LLMMessage

    provider = ExternalProvider(
        base_url=base_url,
        model=model,
        api_key=api_key,
        provider_name="google",
    )
    info = provider.get_model_info()
    print(f"provider={info['provider']} model={info['model']} base_url={info['base_url']}")

    print("[1/2] health_check() ...")
    healthy = await provider.health_check()
    print(f"  health={'OK' if healthy else 'FAIL'}")
    if not healthy:
        print("  (API key missing/invalid or endpoint unreachable — generation skipped)")
        return 1

    print("[2/2] generate() simple prompt ...")
    response = await provider.generate(
        messages=[LLMMessage(role="user", content=prompt)],
        temperature=0.2,
        max_tokens=100,
    )
    if response.error_msg:
        print(f"  generation=FAIL error={response.error_msg}")
        return 1
    print(f"  generation=OK model={response.model}")
    print(f"  content={response.content!r}")
    return 0


def main() -> int:
    from core.config import get_settings

    settings = get_settings()
    parser = argparse.ArgumentParser(description="Manual Google provider check (real network).")
    parser.add_argument("--api-key", default=settings.google_api_key)
    parser.add_argument("--base-url", default=settings.google_base_url)
    parser.add_argument("--model", default=settings.google_model)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--prompt", default="Responda somente: OK")
    args = parser.parse_args()
    if not args.api_key:
        print("Missing API key: set JARVIS_GOOGLE_API_KEY or pass --api-key (value never printed).")
        return 1
    return asyncio.run(_amain(args.api_key, args.base_url, args.model, args.timeout, args.prompt))


if __name__ == "__main__":
    raise SystemExit(main())
