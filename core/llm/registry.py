"""Provider Registry — manages LLM provider registration, health state, and candidate selection."""

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

from core.contracts.llm import BaseLLMProvider
from core.logger import get_logger

logger = get_logger("jarvis.llm.registry")

HealthCheckFn = Callable[[], Coroutine[Any, Any, bool]]


@dataclass
class ProviderEntry:
    """A registered provider with metadata and health state."""
    name: str
    provider: BaseLLMProvider
    priority: float = 1.0
    capabilities: List[str] = field(default_factory=lambda: ["text_generation"])
    health_check: Optional[HealthCheckFn] = None
    cost_weight: float = 0.0
    local: bool = True

    # Health state (managed internally)
    _healthy: bool = True
    _last_health_check: float = 0.0
    _health_ttl: float = 60.0

    @property
    def is_healthy(self) -> bool:
        return self._healthy


class ProviderRegistry:
    """Registry of LLM providers with health caching and candidate selection.

    Providers are registered with a name, priority, and capabilities.
    The registry caches health check results with a configurable TTL.
    """

    def __init__(self, health_ttl: float = 60.0):
        self._providers: Dict[str, ProviderEntry] = {}
        self._health_ttl = health_ttl

    def register(
        self,
        name: str,
        provider: BaseLLMProvider,
        priority: float = 1.0,
        capabilities: Optional[List[str]] = None,
        health_check: Optional[HealthCheckFn] = None,
        cost_weight: float = 0.0,
        local: bool = True,
    ) -> None:
        self._providers[name] = ProviderEntry(
            name=name,
            provider=provider,
            priority=priority,
            capabilities=capabilities or ["text_generation"],
            health_check=health_check or provider.health_check,
            cost_weight=cost_weight,
            local=local,
        )
        logger.info("Registered provider: %s (priority=%.1f, local=%s)", name, priority, local)

    def unregister(self, name: str) -> bool:
        if name in self._providers:
            del self._providers[name]
            logger.info("Unregistered provider: %s", name)
            return True
        return False

    def get(self, name: str) -> Optional[ProviderEntry]:
        return self._providers.get(name)

    def list_providers(self) -> List[ProviderEntry]:
        return list(self._providers.values())

    async def check_health(self, name: str) -> bool:
        entry = self._providers.get(name)
        if not entry:
            return False

        now = time.monotonic()
        if now - entry._last_health_check < entry._health_ttl:
            return entry._healthy

        # Use the provider's health_check method dynamically
        try:
            entry._healthy = await entry.provider.health_check()
        except Exception:
            entry._healthy = False

        entry._last_health_check = now
        return entry._healthy

    async def check_all_health(self) -> Dict[str, bool]:
        results = {}
        for name in self._providers:
            results[name] = await self.check_health(name)
        return results

    def invalidate_health(self, name: str) -> None:
        entry = self._providers.get(name)
        if entry:
            entry._last_health_check = 0.0

    async def get_candidates(
        self,
        task_type: Optional[str] = None,
        require_healthy: bool = True,
    ) -> List[ProviderEntry]:
        candidates = []

        for entry in self._providers.values():
            if require_healthy:
                healthy = await self.check_health(entry.name)
                if not healthy:
                    continue

            if task_type and task_type not in entry.capabilities:
                continue

            candidates.append(entry)

        candidates.sort(key=lambda e: e.priority, reverse=True)
        return candidates

    @property
    def provider_count(self) -> int:
        return len(self._providers)

    @property
    def healthy_count(self) -> int:
        return sum(1 for e in self._providers.values() if e._healthy)


_provider_registry: Optional[ProviderRegistry] = None


def get_provider_registry() -> ProviderRegistry:
    global _provider_registry
    if _provider_registry is None:
        _provider_registry = ProviderRegistry()
    return _provider_registry
