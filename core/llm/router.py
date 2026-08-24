"""Intelligence Router — selects the best available LLM provider with fallback and circuit breaker."""

import time
from typing import Any, Dict, List, Optional

from core.contracts.llm import (
    BaseLLMProvider,
    LLMMessage,
    LLMResponse,
    LLMToolDef,
    StreamChunk,
)
from core.llm.registry import ProviderEntry, ProviderRegistry, get_provider_registry
from core.events.bus import get_event_bus
from core.events.models import EventType, SystemEvent
from core.logger import get_logger

logger = get_logger("jarvis.llm.router")

CIRCUIT_BREAKER_FAILURE_THRESHOLD = 3
CIRCUIT_BREAKER_COOLDOWN_SECONDS = 60.0


class CircuitBreaker:
    """Tracks consecutive failures per provider to avoid hammering broken services."""

    def __init__(
        self,
        failure_threshold: int = CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        cooldown_seconds: float = CIRCUIT_BREAKER_COOLDOWN_SECONDS,
    ):
        self._failure_threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._failures: Dict[str, int] = {}
        self._open_until: Dict[str, float] = {}

    def record_failure(self, name: str) -> None:
        self._failures[name] = self._failures.get(name, 0) + 1
        if self._failures[name] >= self._failure_threshold:
            self._open_until[name] = time.monotonic() + self._cooldown
            logger.warning(
                "Circuit breaker OPEN for %s (failures=%d, cooldown=%.0fs)",
                name, self._failures[name], self._cooldown,
            )

    def record_success(self, name: str) -> None:
        self._failures[name] = 0
        self._open_until.pop(name, None)

    def is_open(self, name: str) -> bool:
        open_until = self._open_until.get(name, 0)
        if time.monotonic() >= open_until:
            if open_until > 0:
                logger.info("Circuit breaker HALF_OPEN for %s", name)
                self._open_until.pop(name, None)
                return False
            return False
        return True

    def reset(self, name: str) -> None:
        self._failures[name] = 0
        self._open_until.pop(name, None)


class IntelligenceRouter:
    """Routes LLM requests to the best available provider with automatic fallback.

    Flow:
    1. Get healthy candidates from ProviderRegistry
    2. Filter out providers with open circuit breakers
    3. Score remaining providers by priority, cost, capabilities
    4. Try best provider
    5. On failure: record in circuit breaker, try next
    6. If all fail: return error response
    """

    def __init__(
        self,
        registry: Optional[ProviderRegistry] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ):
        self._registry = registry or get_provider_registry()
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._event_bus = get_event_bus()

    def _score_provider(self, entry: ProviderEntry, task_type: Optional[str] = None) -> float:
        score = entry.priority
        score -= entry.cost_weight * 0.3

        if task_type and task_type in entry.capabilities:
            score += 0.2

        return score

    def _filter_candidates(
        self,
        candidates: List[ProviderEntry],
        task_type: Optional[str] = None,
    ) -> List[ProviderEntry]:
        filtered = []
        for entry in candidates:
            if self._circuit_breaker.is_open(entry.name):
                logger.debug("Skipping %s (circuit breaker open)", entry.name)
                continue
            if task_type and task_type not in entry.capabilities:
                continue
            filtered.append(entry)

        filtered.sort(key=lambda e: self._score_provider(e, task_type), reverse=True)
        return filtered

    async def route(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMToolDef]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        task_type: Optional[str] = None,
    ) -> LLMResponse:
        """Route an LLM request through providers with fallback."""
        await self._event_bus.publish(SystemEvent(
            event_type=EventType.ROUTING_STARTED,
            source="intelligence_router",
            data={"task_type": task_type or "unknown"},
        ))

        all_candidates = await self._registry.get_candidates(task_type=task_type)
        candidates = self._filter_candidates(all_candidates, task_type)

        if not candidates:
            logger.error("No healthy providers available")
            await self._event_bus.publish(SystemEvent(
                event_type=EventType.PROVIDER_OFFLINE,
                source="intelligence_router",
                data={"reason": "no_healthy_providers"},
            ))
            return LLMResponse(
                content=None,
                tool_calls=[],
                finish_reason="stop",
                error_msg="No healthy LLM providers available. Check Ollama or configure an external provider.",
            )

        last_error = None
        for entry in candidates:
            logger.info("Trying provider: %s", entry.name)

            await self._event_bus.publish(SystemEvent(
                event_type=EventType.PROVIDER_SELECTED,
                source="intelligence_router",
                data={"provider": entry.name, "model": entry.provider.get_model_info().get("model", "")},
            ))

            start = time.monotonic()
            response = await entry.provider.generate(
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            latency_ms = (time.monotonic() - start) * 1000

            if response.error_msg:
                logger.warning("Provider %s failed: %s", entry.name, response.error_msg)
                self._circuit_breaker.record_failure(entry.name)

                await self._event_bus.publish(SystemEvent(
                    event_type=EventType.PROVIDER_FAILED,
                    source="intelligence_router",
                    data={
                        "provider": entry.name,
                        "error": response.error_msg,
                        "latency_ms": round(latency_ms, 1),
                    },
                ))

                last_error = response.error_msg
                continue

            self._circuit_breaker.record_success(entry.name)
            logger.info("Provider %s responded in %.0fms", entry.name, latency_ms)
            return response

        return LLMResponse(
            content=None,
            tool_calls=[],
            finish_reason="stop",
            error_msg=f"All providers failed. Last error: {last_error}",
        )

    async def route_stream(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMToolDef]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        task_type: Optional[str] = None,
    ):
        """Route a streaming LLM request. Yields StreamChunks from the first healthy provider."""
        all_candidates = await self._registry.get_candidates(task_type=task_type)
        candidates = self._filter_candidates(all_candidates, task_type)

        if not candidates:
            yield StreamChunk(content_delta="", finish_reason="stop")
            return

        for entry in candidates:
            try:
                async for chunk in entry.provider.generate_stream(
                    messages=messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    yield chunk

                self._circuit_breaker.record_success(entry.name)
                return
            except Exception as e:
                logger.warning("Streaming failed on %s: %s", entry.name, str(e))
                self._circuit_breaker.record_failure(entry.name)
                continue

        yield StreamChunk(content_delta="", finish_reason="stop")

    def get_status(self) -> Dict[str, Any]:
        providers = []
        for entry in self._registry.list_providers():
            providers.append({
                "name": entry.name,
                "healthy": entry.is_healthy,
                "priority": entry.priority,
                "circuit_open": self._circuit_breaker.is_open(entry.name),
                "capabilities": entry.capabilities,
                "local": entry.local,
                "model": entry.provider.get_model_info().get("model", ""),
            })
        return {
            "providers": providers,
            "healthy_count": self._registry.healthy_count,
            "total_count": self._registry.provider_count,
        }

    async def is_next_provider_local(self, task_type: Optional[str] = None) -> bool:
        """Check if the next provider in the routing chain is local.

        Used to decide tool visibility before calling the LLM.
        Returns True if no candidates exist (safe default).
        """
        all_candidates = await self._registry.get_candidates(task_type=task_type)
        candidates = self._filter_candidates(all_candidates, task_type)
        if not candidates:
            return True
        return candidates[0].local
