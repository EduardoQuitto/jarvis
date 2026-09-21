"""Security test for Bug 4: LOCAL_ONLY names must not leak into the system
prompt when the selected provider is not local (e.g. Gemini).

The prompt must name exactly the tools whose schemas were sent.
"""

import pytest

from core.contracts.enums import ToolVisibility
from core.contracts.llm import LLMResponse
from core.contracts.orchestrator import OrchestratorRequest
from core.llm.mock_provider import MockLLMProvider
from core.orchestrator.engine import Orchestrator
from tools.registry import get_tool_registry


class _RecordingProvider(MockLLMProvider):
    """Mock provider that records the exact messages/tools it received."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen_messages = None
        self.seen_tools = None

    async def generate(self, messages, tools=None, **kwargs):
        self.seen_messages = messages
        self.seen_tools = tools or []
        return await super().generate(messages, tools, **kwargs)


class _NonLocalRouter:
    """Duck-typed router: non-local next provider, records nothing itself."""

    def __init__(self, provider):
        self._provider = provider

    async def is_next_provider_local(self, task_type=None):
        return False

    async def route(self, messages, tools=None, **kwargs):
        return await self._provider.generate(messages, tools, **kwargs)


@pytest.mark.asyncio
async def test_cloud_prompt_hides_local_only_tools():
    provider = _RecordingProvider()
    provider.set_responses([LLMResponse(content="nothing to do", tool_calls=[], finish_reason="stop")])
    orch = Orchestrator(router=_NonLocalRouter(provider))

    await orch.process_message(
        OrchestratorRequest(message="hello", device_id="test-device")
    )

    assert provider.seen_messages, "LLM was never called"
    system_text = provider.seen_messages[0].content

    registry = get_tool_registry()
    shared = {t.name for t in registry.list_tools() if t.visibility == ToolVisibility.SHARED}
    local_only = {t.name for t in registry.list_tools() if t.visibility == ToolVisibility.LOCAL_ONLY}
    assert shared, "test premise broken: no SHARED tools registered"
    assert local_only, "test premise broken: no LOCAL_ONLY tools registered"

    # 1. Schemas sent to the cloud provider are SHARED-only.
    sent_names = {t.function.name for t in provider.seen_tools}
    assert sent_names == shared

    # 2. No LOCAL_ONLY name appears anywhere in the system prompt...
    for name in local_only:
        assert name not in system_text, f"LOCAL_ONLY tool leaked into prompt: {name}"

    # 3. ...while SHARED names are still advertised normally.
    for name in shared:
        assert name in system_text, f"SHARED tool missing from prompt: {name}"


@pytest.mark.asyncio
async def test_local_prompt_still_lists_everything():
    provider = _RecordingProvider()
    provider.set_responses([LLMResponse(content="ok", tool_calls=[], finish_reason="stop")])

    class _LocalRouter(_NonLocalRouter):
        async def is_next_provider_local(self, task_type=None):
            return True

    orch = Orchestrator(router=_LocalRouter(provider))
    await orch.process_message(
        OrchestratorRequest(message="hello", device_id="test-device")
    )

    registry = get_tool_registry()
    all_names = {t.name for t in registry.list_tools()}
    assert {t.function.name for t in provider.seen_tools} == all_names
    assert "launch_application" in provider.seen_messages[0].content
