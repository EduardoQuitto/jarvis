"""LLM Provider Factory — creates providers and the IntelligenceRouter from configuration."""

from typing import Optional

from core.contracts.llm import BaseLLMProvider
from core.config import get_settings
from core.logger import get_logger

logger = get_logger("jarvis.llm.factory")


def create_llm_provider(
    provider_name: Optional[str] = None,
    **kwargs,
) -> BaseLLMProvider:
    """Create an LLM provider instance based on the configured provider name.

    Args:
        provider_name: Override for settings.llm_provider. Values: "ollama", "external", "google", "mock".
        **kwargs: Extra arguments passed to the provider constructor.

    Returns:
        An instance of BaseLLMProvider.

    Raises:
        ValueError: If the provider name is not supported.
    """
    settings = get_settings()
    name = (provider_name or settings.llm_provider).lower().strip()

    logger.info("Creating LLM provider: %s", name)

    if name == "ollama":
        from core.llm.provider import OllamaProvider
        return OllamaProvider(**kwargs)

    if name == "external":
        from core.llm.external_provider import ExternalProvider
        return ExternalProvider(**kwargs)

    if name == "google":
        from core.llm.external_provider import ExternalProvider
        return ExternalProvider(
            base_url=kwargs.pop("base_url", settings.google_base_url),
            model=kwargs.pop("model", settings.google_model),
            api_key=kwargs.pop("api_key", settings.google_api_key),
            provider_name=kwargs.pop("provider_name", "google"),
            **kwargs,
        )

    if name == "mock":
        from core.llm.mock_provider import MockLLMProvider
        return MockLLMProvider(**kwargs)

    raise ValueError(
        f"Unsupported LLM provider: '{name}'. "
        f"Supported: ollama, external, google, mock. "
        f"Set JARVIS_LLM_PROVIDER env var to one of these."
    )


def create_router():
    """Create a fully configured IntelligenceRouter with all available providers.

    Providers are registered based on configuration:
    - Ollama is always registered (priority 10) — will fail health check if unavailable
    - External is registered if external_llm_base_url is configured (priority 5)
    - Google is registered if google_api_key + google_base_url are configured (priority 7)
    - Mock is registered as fallback (priority 1)
    """
    from core.llm.registry import ProviderRegistry, get_provider_registry
    from core.llm.router import IntelligenceRouter

    settings = get_settings()
    registry = get_provider_registry()

    # Only register if not already registered
    if registry.provider_count == 0:
        # 1. Ollama (local, highest priority)
        from core.llm.provider import OllamaProvider
        ollama = OllamaProvider()
        registry.register(
            name="ollama",
            provider=ollama,
            priority=10.0,
            capabilities=["text_generation"],
        )

        # 2. External provider (if configured)
        if settings.external_llm_base_url and settings.external_llm_api_key:
            from core.llm.external_provider import ExternalProvider
            external = ExternalProvider()
            registry.register(
                name="external",
                provider=external,
                priority=5.0,
                capabilities=["text_generation"],
                cost_weight=0.5,
                local=False,
            )
            logger.info("External provider configured: %s", settings.external_llm_provider or "external")

        # 3. Google AI Studio (Gemini) cloud fallback (priority 7, non-local).
        # Only when the API key is configured — otherwise Ollama stays primary
        # and the slot stays disabled. Never outranks Ollama (priority 10).
        if settings.google_api_key and settings.google_base_url:
            from core.llm.external_provider import ExternalProvider
            google = ExternalProvider(
                base_url=settings.google_base_url,
                model=settings.google_model,
                api_key=settings.google_api_key,
                provider_name="google",
            )
            registry.register(
                name="google",
                provider=google,
                priority=7.0,
                capabilities=["text_generation"],
                cost_weight=0.5,
                local=False,
            )
            logger.info("Google provider configured: model=%s", settings.google_model)

        # 4. Mock (fallback, always available)
        from core.llm.mock_provider import MockLLMProvider
        mock = MockLLMProvider()
        registry.register(
            name="mock",
            provider=mock,
            priority=1.0,
            capabilities=["text_generation"],
        )

    return IntelligenceRouter(registry=registry)
