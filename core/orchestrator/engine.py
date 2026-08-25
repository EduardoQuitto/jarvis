"""Orchestrator Engine — the central agentic loop of JARVIS.

Receives user messages, consults LLM with tools, executes tool calls,
manages confirmations, and returns structured responses.

Authorization sources for privileged actions:
  1. Confirmation ID — single-use, session-bound, approved via /api/chat/confirm.
  2. Operator direct — REST call with require_node_auth (not via LLM/MCP path).
     The LLM/MCP path NEVER sets operator_direct; only confirmation_id is accepted.
"""

import json
from typing import Any, Dict, List, Optional

from core.contracts.llm import BaseLLMProvider, LLMMessage, LLMToolDef
from core.contracts.orchestrator import (
    OrchestratorRequest,
    OrchestratorResponse,
    OrchestratorToolResult,
)
from core.conversation.manager import ConversationManager
from core.conversation.context_builder import ContextBuilder
from core.orchestrator.tool_executor import ToolExecutor
from core.orchestrator.confirmation import ConfirmationManager, get_confirmation_manager
from core.orchestrator.system_prompt import build_system_prompt
from core.events.bus import get_event_bus
from core.events.models import EventType, SystemEvent
from core.logger import get_logger

logger = get_logger("jarvis.orchestrator")

MAX_TOOL_ITERATIONS = 10


class Orchestrator:
    """The central brain that processes user messages through the LLM + tool loop.

    Accepts either a BaseLLMProvider (direct) or an IntelligenceRouter (multi-provider).
    When an IntelligenceRouter is used, the orchestrator benefits from automatic fallback
    between providers (Ollama -> External -> Mock).

    Flow:
    1. Receive user message (or confirmation response)
    2. If confirmation_id provided: consume -> approve/deny -> resume or cancel
    3. Load conversation context
    4. Build system prompt + tools
    5. Call LLM (via provider or router)
    6. If tool_calls -> policy check -> execute (or pause for confirmation) -> feed back -> loop
    7. If text response -> return
    8. Persist everything
    """

    def __init__(
        self,
        llm_provider: Optional[BaseLLMProvider] = None,
        router: Optional[Any] = None,
        conversation_manager: Optional[ConversationManager] = None,
        tool_executor: Optional[Any] = None,
        confirmation_manager: Optional[ConfirmationManager] = None,
    ):
        self._llm = llm_provider
        self._router = router
        self._conversation = conversation_manager or ConversationManager()
        self._tool_executor = tool_executor or ToolExecutor()
        self._confirmations = confirmation_manager or get_confirmation_manager()
        self._context_builder = ContextBuilder()
        self._event_bus = get_event_bus()

    async def _call_llm(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMToolDef]] = None,
    ):
        """Call the LLM through whatever backend is configured (provider or router)."""
        if self._router is not None:
            return await self._router.route(messages=messages, tools=tools)
        if self._llm is None:
            raise RuntimeError("No LLM provider or router configured")
        return await self._llm.generate(messages=messages, tools=tools)

    async def _build_tools_list(self):
        """Build the tools list for the current session.

        If the next provider is external, only SHARED tools are sent.
        """
        from tools.registry import get_tool_registry
        from tools import register_default_tools
        registry = get_tool_registry()
        register_default_tools(registry)

        shared_only = False
        if self._router is not None:
            shared_only = not await self._router.is_next_provider_local()

        return registry, self._context_builder.build_tools_list(
            registry.list_tools(), shared_only=shared_only,
        )

    def _build_tool_result_message(self, tool_name, call_id, tool_result, security_level):
        """Convert a tool result to an LLM message."""
        from core.llm.converters import tool_result_to_message
        from core.contracts.tool import ToolResult as TR
        from core.contracts.enums import SecurityLevel
        tr = TR(
            success=tool_result.success,
            data=tool_result.data,
            error=tool_result.error,
            execution_time_ms=tool_result.execution_time_ms,
            security_level=security_level if tool_result.success else SecurityLevel.GREEN,
        )
        return tool_result_to_message(tool_name, call_id, tr)

    async def process_message(self, request: OrchestratorRequest) -> OrchestratorResponse:
        """Main entry point: process a user message through the agentic loop."""
        logger.info("Processing message from device '%s': %s...", request.device_id, request.message[:80])

        # Create or use existing session
        session_id = request.session_id
        if not session_id:
            session_id = await self._conversation.create_session(
                title=request.message[:50],
                device_id=request.device_id,
            )

        # Handle confirmation/denial responses
        if request.confirmation_id:
            # If caller provides explicit approval decision, apply it first
            if request.approved is True:
                self._confirmations.approve(request.confirmation_id)
            elif request.approved is False:
                self._confirmations.deny(request.confirmation_id)

            cid_result = self._confirmations.consume(
                request.confirmation_id,
                session_id=session_id,
            )

            if cid_result is None:
                return OrchestratorResponse(
                    session_id=session_id,
                    response_text="Confirmation not found, already used, or not yet resolved.",
                    needs_confirmation=False,
                )

            if not cid_result["approved"]:
                await self._conversation.append_message(
                    session_id, "assistant",
                    f"Action '{cid_result['tool_name']}' denied by user.",
                )
                return OrchestratorResponse(
                    session_id=session_id,
                    response_text=f"Action '{cid_result['tool_name']}' denied.",
                    needs_confirmation=False,
                )

            # Approved: execute the pending tool call via operator source
            logger.info("Resuming confirmed tool: %s (cid=%s)", cid_result["tool_name"], request.confirmation_id)

            registry, tools = await self._build_tools_list()
            tool = registry.get(cid_result["tool_name"])

            result = await self._tool_executor.execute_tool_call(
                tool_name=cid_result["tool_name"],
                arguments=cid_result["arguments"],
                call_id=cid_result["call_id"] or "confirmed",
                source="operator",
            )

            await self._event_bus.publish(SystemEvent(
                event_type=EventType.TOOL_RESULT,
                source="orchestrator",
                data={
                    "tool_name": cid_result["tool_name"],
                    "call_id": cid_result["call_id"],
                    "success": result.success,
                    "error": result.error,
                },
            ))

            # Feed the result to the LLM for a final response
            tool_msg = self._build_tool_result_message(
                cid_result["tool_name"], cid_result["call_id"], result,
                tool.metadata.security_level if tool else None,
            )

            history = await self._conversation.get_context_window(session_id)
            system_prompt = build_system_prompt(
                device_id=request.device_id,
                device_capabilities=request.device_capabilities,
                available_tool_names=[t.name for t in registry.list_tools()],
            )
            messages = self._context_builder.build(
                system_prompt=system_prompt,
                conversation_messages=history,
            )
            messages.append(tool_msg)

            # Single LLM call to summarize the result
            response = await self._call_llm(messages=messages, tools=tools)
            final_text = response.content or "Action completed."
            await self._conversation.append_message(session_id, "assistant", final_text)

            return OrchestratorResponse(
                session_id=session_id,
                response_text=final_text,
                tool_calls_made=[result],
                iterations_used=1,
            )

        # Append user message
        await self._conversation.append_message(session_id, "user", request.message)

        # Publish user message event
        await self._event_bus.publish(SystemEvent(
            event_type=EventType.USER_MESSAGE,
            source=request.device_id,
            data={"session_id": session_id, "message": request.message},
        ))

        # Get conversation history
        history = await self._conversation.get_context_window(session_id)

        # Build system prompt
        registry, tools = await self._build_tools_list()
        tool_names = [t.name for t in registry.list_tools()]
        system_prompt = build_system_prompt(
            device_id=request.device_id,
            device_capabilities=request.device_capabilities,
            available_tool_names=tool_names,
        )

        # Build full context
        messages = self._context_builder.build(
            system_prompt=system_prompt,
            conversation_messages=history,
        )

        # Agentic loop
        all_tool_results: List[OrchestratorToolResult] = []
        iterations = 0
        final_text = ""

        await self._event_bus.publish(SystemEvent(
            event_type=EventType.SYSTEM_STATUS,
            source="orchestrator",
            data={"status": "THINKING", "session_id": session_id},
        ))

        while iterations < MAX_TOOL_ITERATIONS:
            iterations += 1
            logger.info("LLM iteration %d/%d", iterations, MAX_TOOL_ITERATIONS)

            # Call LLM (via provider or router)
            response = await self._call_llm(messages=messages, tools=tools)

            # Handle LLM error
            if response.error_msg:
                logger.error("LLM returned error: %s", response.error_msg)
                final_text = f"I encountered an error: {response.error_msg}"
                await self._conversation.append_message(session_id, "assistant", final_text)
                return OrchestratorResponse(
                    session_id=session_id,
                    response_text=final_text,
                    tool_calls_made=all_tool_results,
                    iterations_used=iterations,
                    error=response.error_msg,
                )

            # If no tool calls, we have a text response
            if not response.tool_calls:
                final_text = response.content or ""
                await self._conversation.append_message(session_id, "assistant", final_text)
                break

            # Process tool calls
            assistant_msg = LLMMessage(
                role="assistant",
                content=response.content or "",
                tool_calls=response.tool_calls,
            )
            messages.append(assistant_msg)

            for tc in response.tool_calls:
                tool_name = tc.function.name
                arguments = tc.function.arguments
                call_id = tc.id

                logger.info("Tool call: %s(%s)", tool_name, json.dumps(arguments)[:100])

                await self._event_bus.publish(SystemEvent(
                    event_type=EventType.TOOL_CALL,
                    source="orchestrator",
                    data={"tool_name": tool_name, "arguments": arguments, "call_id": call_id},
                ))

                # Check policy — NEVER pass confirmed=True from LLM path
                tool = registry.get(tool_name)
                if tool:
                    from security.policy_engine import PolicyEngine
                    policy = PolicyEngine()
                    decision = policy.evaluate(
                        tool.metadata, arguments, confirmed=False, source="orchestrator",
                    )

                    if not decision.allowed and decision.requires_confirmation:
                        cid = await self._confirmations.request_confirmation(
                            tool_name=tool_name,
                            arguments=arguments,
                            security_level=tool.metadata.security_level.value,
                            reason=decision.reason,
                            session_id=session_id,
                            call_id=call_id,
                        )

                        await self._event_bus.publish(SystemEvent(
                            event_type=EventType.WAITING_CONFIRMATION,
                            source="orchestrator",
                            data={
                                "confirmation_id": cid,
                                "tool_name": tool_name,
                                "arguments": arguments,
                                "security_level": tool.metadata.security_level.value,
                                "reason": decision.reason,
                            },
                        ))

                        status_msg = f"[Action requires confirmation: {tool_name}]"
                        await self._conversation.append_message(session_id, "assistant", status_msg)

                        return OrchestratorResponse(
                            session_id=session_id,
                            response_text=f"I need your confirmation to execute '{tool_name}'. "
                                          f"Security level: {tool.metadata.security_level.value}. "
                                          f"{decision.reason}",
                            tool_calls_made=all_tool_results,
                            needs_confirmation=True,
                            confirmation_id=cid,
                            confirmation_details=f"Tool: {tool_name}, Arguments: {json.dumps(arguments)}",
                            iterations_used=iterations,
                        )

                    if not decision.allowed:
                        # Denied (not just "needs confirmation")
                        tool_msg = self._build_tool_result_message(
                            tool_name, call_id,
                            type('FakeResult', (), {
                                'success': False, 'data': None, 'error': decision.reason,
                                'execution_time_ms': 0, 'security_level': tool.metadata.security_level,
                            })(),
                            tool.metadata.security_level,
                        )
                        messages.append(tool_msg)
                        continue

                # Execute the tool (GREEN or operator-approved) via orchestrator source
                result = await self._tool_executor.execute_tool_call(
                    tool_name=tool_name,
                    arguments=arguments,
                    call_id=call_id,
                    source="orchestrator",
                )
                all_tool_results.append(result)

                await self._event_bus.publish(SystemEvent(
                    event_type=EventType.TOOL_RESULT,
                    source="orchestrator",
                    data={
                        "tool_name": tool_name,
                        "call_id": call_id,
                        "success": result.success,
                        "error": result.error,
                    },
                ))

                # Add tool result to context for LLM
                tool_msg = self._build_tool_result_message(
                    tool_name, call_id, result,
                    tool.metadata.security_level if tool else None,
                )
                messages.append(tool_msg)

        if iterations >= MAX_TOOL_ITERATIONS and not final_text:
            final_text = "I've reached the maximum number of tool call iterations. Please try a simpler request."
            await self._conversation.append_message(session_id, "assistant", final_text)

        await self._event_bus.publish(SystemEvent(
            event_type=EventType.ASSISTANT_RESPONSE,
            source="orchestrator",
            data={"session_id": session_id, "response": final_text[:200]},
        ))

        return OrchestratorResponse(
            session_id=session_id,
            response_text=final_text,
            tool_calls_made=all_tool_results,
            iterations_used=iterations,
        )
