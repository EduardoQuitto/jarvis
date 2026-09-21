"""Orchestrator Engine — the central agentic loop of JARVIS.

Receives user messages, consults LLM with tools, executes tool calls,
manages confirmations, and returns structured responses.

Authorization sources for privileged actions:
  1. Confirmation ID — single-use, session-bound, approved via /api/chat/confirm.
  2. Operator direct — REST call with require_node_auth (not via LLM/MCP path).
     The LLM/MCP path NEVER sets operator_direct; only confirmation_id is accepted.
"""

import asyncio
import json
from typing import Any, AsyncGenerator, Dict, List, Optional

from core.contracts.llm import (
    BaseLLMProvider,
    LLMFunctionCall,
    LLMMessage,
    LLMResponse,
    LLMToolCall,
    LLMToolDef,
)
from core.contracts.orchestrator import (
    OrchestratorMessageType,
    OrchestratorRequest,
    OrchestratorResponse,
    OrchestratorStreamEvent,
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


def _preview_data(data: Any, limit: int = 2000) -> Any:
    """Size-guarded preview of a tool result payload for streaming.

    Tool results can be large (e.g. base64 screenshots); the full payload
    stays in history, only a bounded preview travels over SSE.
    """
    try:
        text = data if isinstance(data, str) else json.dumps(data, default=str)
    except Exception:
        return {"_unserializable": True}
    if len(text) > limit:
        return text[:limit] + "...[truncated]"
    return data


class _StreamTurnAccumulator:
    """Buffers one streamed LLM turn: live text plus tool calls.

    Two delta shapes are accepted:
    - complete LLMToolCall objects (e.g. MockLLMProvider) — stored directly;
    - RawToolCallDelta fragments (Ollama/External) — argument strings are
      concatenated per call id IN ORDER and parsed exactly once at turn end.
      A fragment is never parsed alone, so split JSON is never lost.
    """

    def __init__(self):
        self.text = ""
        self.calls = {}
        self.raw = {}

    def add_tool_delta(self, call) -> None:
        """Merge one complete tool call by id (supersedes any raw fragments)."""
        self.raw.pop(call.id, None)
        existing = self.calls.get(call.id)
        if existing is None:
            self.calls[call.id] = call
            return
        if call.function.name:
            existing.function.name = call.function.name
        if call.function.arguments:
            if isinstance(existing.function.arguments, dict) and isinstance(call.function.arguments, dict):
                existing.function.arguments.update(call.function.arguments)
            else:
                existing.function.arguments = call.function.arguments

    def add_tool_raw(self, fragment) -> None:
        """Append one raw argument fragment, preserving arrival order."""
        slot = self.raw.setdefault(fragment.id, {"name": "", "parts": []})
        if fragment.name and not slot["name"]:
            slot["name"] = fragment.name
        if fragment.arguments_str:
            slot["parts"].append(fragment.arguments_str)

    def finalize_calls(self):
        """Parse buffered raw fragments now that the turn ended.

        Returns (calls, error): calls is the ordered list of complete
        LLMToolCall objects; error is None on success. On invalid JSON (or
        missing name) error names the call — the caller must NOT execute it.
        """
        merged = dict(self.calls)
        for call_id, slot in self.raw.items():
            name = slot["name"]
            if not name:
                return None, (
                    f"Tool call '{call_id}' arrived without a function name; "
                    f"tool not executed."
                )
            full = "".join(slot["parts"]).strip()
            try:
                arguments = json.loads(full) if full else {}
            except json.JSONDecodeError as exc:
                return None, (
                    f"Tool call arguments for '{name}' (call '{call_id}') are not "
                    f"valid JSON after the full stream ({exc}); tool not executed."
                )
            if not isinstance(arguments, dict):
                return None, (
                    f"Tool call arguments for '{name}' (call '{call_id}') must be "
                    f"a JSON object; tool not executed."
                )
            merged[call_id] = LLMToolCall(
                id=call_id,
                type="function",
                function=LLMFunctionCall(name=name, arguments=arguments),
            )
        return list(merged.values()), None


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

    def _stream_event(self, event_type: OrchestratorMessageType, **data: Any) -> OrchestratorStreamEvent:
        """Build one structured streaming event (SSE name = type lowercased)."""
        return OrchestratorStreamEvent(event_type=event_type, data=data)

    async def _iter_llm_stream(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[LLMToolDef]],
        acc: "_StreamTurnAccumulator",
    ) -> AsyncGenerator[str, None]:
        """Yield live text deltas from the provider/router stream.

        Selection and fallback stay inside route_stream()/generate_stream —
        never duplicated here. Tool-call deltas are buffered into acc.
        """
        if self._router is not None:
            stream = self._router.route_stream(messages=messages, tools=tools)
        elif self._llm is not None:
            stream = self._llm.generate_stream(messages=messages, tools=tools)
        else:
            raise RuntimeError("No LLM provider or router configured")
        async for chunk in stream:
            if chunk.content_delta:
                acc.text += chunk.content_delta
                yield chunk.content_delta
            for call in chunk.tool_calls_deltas or []:
                acc.add_tool_delta(call)
            for fragment in chunk.tool_calls_raw or []:
                acc.add_tool_raw(fragment)

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

    async def _persist_tool_result(self, session_id, tool_msg) -> None:
        """Persist one tool result so restarts keep a valid sequence.

        The message persisted is byte-identical in content to what the LLM
        saw, so a reloaded context matches the live one.
        """
        await self._conversation.append_message(
            session_id, "tool", tool_msg.content or "",
            tool_call_id=tool_msg.tool_call_id, name=tool_msg.name,
        )

    async def _process_single_call(
        self, registry, tool_name, arguments, call_id, session_id, remaining_calls,
    ) -> dict:
        """Policy-gate and run ONE LLM-requested tool call (orchestrator source).

        Every tool result is persisted exactly once via _persist_tool_result.
        NEVER passes confirmed=True: approvals only arrive through consumed
        confirmation ids handled by the caller. A new confirmation request
        carries `remaining_calls` so the turn can continue on resume.

        Returns {"action": "executed", "result", "tool_msg"},
                {"action": "denied", "tool_msg"} (policy denial feedback), or
                {"action": "confirm", "confirmation_id", "confirmation_details",
                 "tool_name", "security_level", "reason"}.
        """
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
                    remaining_calls=remaining_calls,
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

                return {
                    "action": "confirm",
                    "confirmation_id": cid,
                    "confirmation_details": f"Tool: {tool_name}, Arguments: {json.dumps(arguments)}",
                    "tool_name": tool_name,
                    "security_level": tool.metadata.security_level.value,
                    "reason": decision.reason,
                }

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
                await self._persist_tool_result(session_id, tool_msg)
                return {"action": "denied", "tool_msg": tool_msg}

        # Execute the tool (GREEN or operator-approved) via orchestrator source
        result = await self._tool_executor.execute_tool_call(
            tool_name=tool_name,
            arguments=arguments,
            call_id=call_id,
            source="orchestrator",
        )

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

        tool_msg = self._build_tool_result_message(
            tool_name, call_id, result,
            tool.metadata.security_level if tool else None,
        )
        await self._persist_tool_result(session_id, tool_msg)
        return {"action": "executed", "result": result, "tool_msg": tool_msg}

    async def _resume_remaining_calls(self, registry, cid_result, session_id):
        """Process sibling calls left over from a confirmed assistant turn.

        Each call goes through the same policy gate (orchestrator source,
        never pre-confirmed). Returns (results, confirm_outcome) where
        confirm_outcome is None unless another call needs confirmation —
        in which case it carries a fresh confirmation request and the turn
        pauses again without breaking the sequence.
        """
        results = []
        remaining = cid_result.get("remaining_calls") or []
        for pos, item in enumerate(remaining):
            outcome = await self._process_single_call(
                registry,
                item["tool_name"], item["arguments"], item["call_id"],
                session_id, remaining[pos + 1:],
            )
            if outcome["action"] == "confirm":
                return results, outcome
            if outcome["action"] == "executed":
                results.append(outcome["result"])
            # Denied feedback is already persisted; keep going with the rest.
        return results, None

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
                # Close the pending tool call with an honest tool result so
                # the sequence stays valid (assistant(tc) -> tool -> assistant).
                # A bare denial text would leave the call unanswered, which
                # OpenAI-compatible providers reject.
                denied_msg = LLMMessage(
                    role="tool",
                    content=f"Action '{cid_result['tool_name']}' was denied by the user and was not executed.",
                    tool_call_id=cid_result["call_id"] or "denied",
                    name=cid_result["tool_name"],
                )
                await self._persist_tool_result(session_id, denied_msg)
                # Sibling calls of the same turn still get their own policy
                # gate: denying one call does not cancel the others. They run
                # BEFORE the denial text is persisted, so no assistant message
                # ever interrupts pending tool calls.
                registry, _ = await self._build_tools_list()
                remaining_results, confirm = await self._resume_remaining_calls(
                    registry, cid_result, session_id,
                )
                if confirm is not None:
                    return OrchestratorResponse(
                        session_id=session_id,
                        response_text=f"I need your confirmation to execute '{confirm['tool_name']}'. "
                                      f"Security level: {confirm['security_level']}. "
                                      f"{confirm['reason']}",
                        tool_calls_made=remaining_results,
                        needs_confirmation=True,
                        confirmation_id=confirm["confirmation_id"],
                        confirmation_details=confirm["confirmation_details"],
                        iterations_used=1,
                    )
                await self._conversation.append_message(
                    session_id, "assistant",
                    f"Action '{cid_result['tool_name']}' denied by user.",
                )
                return OrchestratorResponse(
                    session_id=session_id,
                    response_text=f"Action '{cid_result['tool_name']}' denied.",
                    needs_confirmation=False,
                    tool_calls_made=remaining_results,
                )

            # Approved: execute the pending tool call via operator source.
            # The confirmation was consumed + approved through the
            # ConfirmationManager (single-use, session-bound), which IS the
            # approval origin — so operator_direct=True propagates the
            # approval to PolicyEngine. Without it, approved YELLOW/RED
            # tools would be denied again here. The LLM path can never set
            # this flag; only this approved-resume branch passes True.
            logger.info("Resuming confirmed tool: %s (cid=%s)", cid_result["tool_name"], request.confirmation_id)

            registry, tools = await self._build_tools_list()
            tool = registry.get(cid_result["tool_name"])

            result = await self._tool_executor.execute_tool_call(
                tool_name=cid_result["tool_name"],
                arguments=cid_result["arguments"],
                call_id=cid_result["call_id"] or "confirmed",
                operator_direct=True,
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
            # Persist the approved tool result. The assistant(tool_calls) turn
            # was already persisted when it was requested — only the result
            # is new here, so this cannot duplicate anything.
            await self._persist_tool_result(session_id, tool_msg)
            results = [result]

            # Continue the same assistant turn: run sibling calls left over
            # in remaining_calls. Only when every call of the turn has exactly
            # one persisted result do we advance to the next LLM call — this
            # keeps the sequence valid for OpenAI-compatible providers.
            remaining_results, confirm = await self._resume_remaining_calls(
                registry, cid_result, session_id,
            )
            results.extend(remaining_results)
            if confirm is not None:
                return OrchestratorResponse(
                    session_id=session_id,
                    response_text=f"I need your confirmation to execute '{confirm['tool_name']}'. "
                                  f"Security level: {confirm['security_level']}. "
                                  f"{confirm['reason']}",
                    tool_calls_made=results,
                    needs_confirmation=True,
                    confirmation_id=confirm["confirmation_id"],
                    confirmation_details=confirm["confirmation_details"],
                    iterations_used=1,
                )

            # History already contains every result persisted above (approved
            # + remaining), so nothing is appended manually here — appending
            # would duplicate them.
            history = await self._conversation.get_context_window(session_id)
            # Names come from the exact tool definitions sent to the provider
            # (already visibility-filtered) — never from the full registry,
            # so LOCAL_ONLY names can't leak into the prompt of a cloud LLM.
            system_prompt = build_system_prompt(
                device_id=request.device_id,
                device_capabilities=request.device_capabilities,
                available_tool_names=[t.function.name for t in tools],
            )
            messages = self._context_builder.build(
                system_prompt=system_prompt,
                conversation_messages=history,
            )

            # Single LLM call to summarize the result. Never mask a tool
            # failure as success when the LLM returns no summary text.
            response = await self._call_llm(messages=messages, tools=tools)
            failed = [r for r in results if not r.success]
            if response.content:
                final_text = response.content
            elif not failed:
                final_text = "Action completed."
            else:
                final_text = f"Action '{failed[0].tool_name}' failed: {failed[0].error}"
            await self._conversation.append_message(session_id, "assistant", final_text)

            return OrchestratorResponse(
                session_id=session_id,
                response_text=final_text,
                tool_calls_made=results,
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

        # Build system prompt. Names come from the exact tool definitions
        # sent to the provider (already visibility-filtered) — never from
        # the full registry, so LOCAL_ONLY names can't leak into the prompt
        # of a cloud LLM.
        registry, tools = await self._build_tools_list()
        tool_names = [t.function.name for t in tools]
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

            # Persist the assistant turn WITH its tool calls (single message).
            # Without this, restarts lose the calls and the reloaded context
            # starts with orphan tool results. The final text turn (if any)
            # is persisted separately when it happens.
            await self._conversation.append_message(
                session_id, "assistant", response.content or "",
                tool_calls_json=json.dumps([tc.model_dump() for tc in response.tool_calls]),
            )

            # NOTE: the pending state is intentionally NOT persisted as an
            # assistant message anywhere below. Persisting it would inject
            # assistant text between assistant(tool_calls) and its tool
            # results, producing an invalid sequence for OpenAI-compatible
            # providers. Pending requests live in the ConfirmationManager and
            # travel in WAITING_CONFIRMATION events + responses instead.
            for idx, tc in enumerate(response.tool_calls):
                # Sibling calls after this one ride along in the confirmation
                # (remaining_calls) so a resume continues the turn instead of
                # dropping them and leaving calls unanswered.
                remaining = [
                    {"tool_name": t.function.name, "arguments": t.function.arguments, "call_id": t.id}
                    for t in response.tool_calls[idx + 1:]
                ]
                outcome = await self._process_single_call(
                    registry, tc.function.name, tc.function.arguments, tc.id,
                    session_id, remaining,
                )
                if outcome["action"] == "confirm":
                    return OrchestratorResponse(
                        session_id=session_id,
                        response_text=f"I need your confirmation to execute '{outcome['tool_name']}'. "
                                      f"Security level: {outcome['security_level']}. "
                                      f"{outcome['reason']}",
                        tool_calls_made=all_tool_results,
                        needs_confirmation=True,
                        confirmation_id=outcome["confirmation_id"],
                        confirmation_details=outcome["confirmation_details"],
                        iterations_used=iterations,
                    )
                if outcome["action"] == "executed":
                    all_tool_results.append(outcome["result"])
                messages.append(outcome["tool_msg"])

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

    async def stream_message(
        self, request: OrchestratorRequest,
    ) -> AsyncGenerator[OrchestratorStreamEvent, None]:
        """Stream orchestrator processing as structured events.

        Mirrors process_message turn for turn (same policy gates, same
        persistence, same confirmation flow) but emits text as live
        text_delta events instead of one final response. Every stream ends
        with done; failures also emit error first. Client disconnects
        surface as CancelledError and are re-raised untouched: the streaming
        path creates no background tasks, so nothing can leak.
        """
        try:
            async for event in self._stream_message_inner(request):
                yield event
        except asyncio.CancelledError:
            logger.info("Chat stream cancelled (client disconnect)")
            raise
        except Exception as e:
            logger.error("Streaming failed: %s", str(e))
            yield self._stream_event(
                OrchestratorMessageType.ERROR, message=f"Streaming failed: {str(e)}",
            )
            yield self._stream_event(
                OrchestratorMessageType.DONE, error=f"Streaming failed: {str(e)}",
            )

    async def _stream_confirmation_resume(self, request: OrchestratorRequest, session_id: str):
        """Stream the confirmation approve/deny resume path."""
        if request.approved is True:
            self._confirmations.approve(request.confirmation_id)
        elif request.approved is False:
            self._confirmations.deny(request.confirmation_id)

        cid_result = self._confirmations.consume(request.confirmation_id, session_id=session_id)

        if cid_result is None:
            message = "Confirmation not found, already used, or not yet resolved."
            yield self._stream_event(OrchestratorMessageType.ERROR, message=message, session_id=session_id)
            yield self._stream_event(OrchestratorMessageType.DONE, session_id=session_id, error=message)
            return

        registry, tools = await self._build_tools_list()

        if not cid_result["approved"]:
            denied_msg_text = f"Action '{cid_result['tool_name']}' was denied by the user and was not executed."
            await self._persist_tool_result(session_id, LLMMessage(
                role="tool", content=denied_msg_text,
                tool_call_id=cid_result["call_id"] or "denied", name=cid_result["tool_name"],
            ))
            # Siblings run before the denial text is persisted (see below).
            remaining_results = []
            async for item in self._drain_remaining_stream(registry, cid_result, session_id, remaining_results):
                if isinstance(item, dict):
                    async for event in self._emit_waiting_confirmation(item, session_id):
                        yield event
                    return
                yield item
            denial_text = f"Action '{cid_result['tool_name']}' denied by user."
            await self._conversation.append_message(session_id, "assistant", denial_text)
            yield self._stream_event(
                OrchestratorMessageType.DONE, session_id=session_id,
                response_text=f"Action '{cid_result['tool_name']}' denied.",
            )
            return

        # Approved: same operator-direct execution as process_message.
        logger.info("Resuming confirmed tool: %s (cid=%s)", cid_result["tool_name"], request.confirmation_id)
        tool = registry.get(cid_result["tool_name"])
        result = await self._tool_executor.execute_tool_call(
            tool_name=cid_result["tool_name"],
            arguments=cid_result["arguments"],
            call_id=cid_result["call_id"] or "confirmed",
            operator_direct=True,
            source="operator",
        )
        await self._event_bus.publish(SystemEvent(
            event_type=EventType.TOOL_RESULT,
            source="orchestrator",
            data={"tool_name": cid_result["tool_name"], "call_id": cid_result["call_id"],
                  "success": result.success, "error": result.error},
        ))
        tool_msg = self._build_tool_result_message(
            cid_result["tool_name"], cid_result["call_id"], result,
            tool.metadata.security_level if tool else None,
        )
        await self._persist_tool_result(session_id, tool_msg)
        yield self._stream_event(
            OrchestratorMessageType.TOOL_RESULT, tool_name=result.tool_name, call_id=result.call_id,
            success=result.success, error=result.error, data_preview=_preview_data(result.data),
            session_id=session_id,
        )
        results = [result]

        async for item in self._drain_remaining_stream(registry, cid_result, session_id, results):
            if isinstance(item, dict):
                async for event in self._emit_waiting_confirmation(item, session_id):
                    yield event
                return
            yield item

        # History already holds every persisted result: rebuild and stream
        # the summary turn live. Tool deltas in a summary turn are ignored,
        # mirroring process_message (single summary call, no new tools).
        history = await self._conversation.get_context_window(session_id)
        system_prompt = build_system_prompt(
            device_id=request.device_id,
            device_capabilities=request.device_capabilities,
            available_tool_names=[t.function.name for t in tools],
        )
        messages = self._context_builder.build(system_prompt=system_prompt, conversation_messages=history)
        acc = _StreamTurnAccumulator()
        async for delta in self._iter_llm_stream(messages, tools, acc):
            yield self._stream_event(OrchestratorMessageType.TEXT_DELTA, text=delta, session_id=session_id)
        failed = [r for r in results if not r.success]
        if acc.text:
            final_text = acc.text
        elif not failed:
            final_text = "Action completed."
        else:
            final_text = f"Action '{failed[0].tool_name}' failed: {failed[0].error}"
        await self._conversation.append_message(session_id, "assistant", final_text)
        yield self._stream_event(
            OrchestratorMessageType.DONE, session_id=session_id,
            response_text=final_text, iterations_used=1,
        )

    async def _drain_remaining_stream(self, registry, cid_result, session_id, results):
        """Process resume-remaining calls, yielding live stream events.

        Appends executed results to `results`. Yields stream events as calls
        complete. Yields the confirm outcome dict (not an event) when another
        call needs confirmation — the caller emits waiting_confirmation.
        """
        remaining = cid_result.get("remaining_calls") or []
        for pos, item in enumerate(remaining):
            yield self._stream_event(
                OrchestratorMessageType.TOOL_CALL, tool_name=item["tool_name"],
                arguments=item["arguments"], call_id=item["call_id"], session_id=session_id,
            )
            outcome = await self._process_single_call(
                registry, item["tool_name"], item["arguments"], item["call_id"],
                session_id, remaining[pos + 1:],
            )
            if outcome["action"] == "confirm":
                yield outcome
                return
            if outcome["action"] == "executed":
                result = outcome["result"]
                results.append(result)
                yield self._stream_event(
                    OrchestratorMessageType.TOOL_RESULT, tool_name=result.tool_name,
                    call_id=result.call_id, success=result.success, error=result.error,
                    data_preview=_preview_data(result.data), session_id=session_id,
                )
            else:
                yield self._stream_event(
                    OrchestratorMessageType.TOOL_RESULT, tool_name=item["tool_name"],
                    call_id=item["call_id"], success=False,
                    error=outcome["tool_msg"].content, session_id=session_id,
                )

    async def _emit_waiting_confirmation(self, confirm: dict, session_id: str):
        """Yield waiting_confirmation + closing done for a fresh confirmation."""
        yield self._stream_event(
            OrchestratorMessageType.WAITING_CONFIRMATION,
            confirmation_id=confirm["confirmation_id"], tool_name=confirm["tool_name"],
            security_level=confirm["security_level"], reason=confirm["reason"],
            session_id=session_id,
        )
        yield self._stream_event(
            OrchestratorMessageType.DONE, session_id=session_id,
            needs_confirmation=True, confirmation_id=confirm["confirmation_id"],
        )

    async def _stream_message_inner(self, request: OrchestratorRequest):
        """Core streaming agentic loop (see stream_message)."""
        session_id = request.session_id
        if not session_id:
            session_id = await self._conversation.create_session(
                title=request.message[:50],
                device_id=request.device_id,
            )
        yield self._stream_event(OrchestratorMessageType.START, session_id=session_id)

        if request.confirmation_id:
            async for event in self._stream_confirmation_resume(request, session_id):
                yield event
            return

        yield self._stream_event(OrchestratorMessageType.THINKING, session_id=session_id)

        await self._conversation.append_message(session_id, "user", request.message)
        await self._event_bus.publish(SystemEvent(
            event_type=EventType.USER_MESSAGE,
            source=request.device_id,
            data={"session_id": session_id, "message": request.message},
        ))

        history = await self._conversation.get_context_window(session_id)
        registry, tools = await self._build_tools_list()
        system_prompt = build_system_prompt(
            device_id=request.device_id,
            device_capabilities=request.device_capabilities,
            available_tool_names=[t.function.name for t in tools],
        )
        messages = self._context_builder.build(
            system_prompt=system_prompt,
            conversation_messages=history,
        )

        all_results = []
        iterations = 0

        await self._event_bus.publish(SystemEvent(
            event_type=EventType.SYSTEM_STATUS,
            source="orchestrator",
            data={"status": "THINKING", "session_id": session_id},
        ))

        while iterations < MAX_TOOL_ITERATIONS:
            iterations += 1
            logger.info("LLM streaming iteration %d/%d", iterations, MAX_TOOL_ITERATIONS)

            acc = _StreamTurnAccumulator()
            async for delta in self._iter_llm_stream(messages, tools, acc):
                yield self._stream_event(
                    OrchestratorMessageType.TEXT_DELTA, text=delta, session_id=session_id,
                )

            if not acc.text and not acc.calls and not acc.raw:
                message = "LLM returned no content (no healthy provider or provider error)."
                logger.error(message)
                yield self._stream_event(OrchestratorMessageType.ERROR, message=message, session_id=session_id)
                yield self._stream_event(
                    OrchestratorMessageType.DONE, session_id=session_id,
                    error=message, iterations_used=iterations,
                )
                return

            # Raw fragments are parsed exactly once, now that the turn ended.
            # Invalid JSON aborts the turn explicitly: the tool is NOT
            # executed, and nothing partial is persisted.
            calls, parse_error = acc.finalize_calls()
            if parse_error is not None:
                logger.error("Streaming turn aborted: %s", parse_error)
                yield self._stream_event(OrchestratorMessageType.ERROR, message=parse_error, session_id=session_id)
                yield self._stream_event(
                    OrchestratorMessageType.DONE, session_id=session_id,
                    error=parse_error, iterations_used=iterations,
                )
                return

            if not calls:
                final_text = acc.text or ""
                await self._conversation.append_message(session_id, "assistant", final_text)
                yield self._stream_event(
                    OrchestratorMessageType.DONE, session_id=session_id,
                    response_text=final_text, iterations_used=iterations,
                    needs_confirmation=False,
                )
                return

            assistant_msg = LLMMessage(
                role="assistant",
                content=acc.text or "",
                tool_calls=calls,
            )
            messages.append(assistant_msg)
            await self._conversation.append_message(
                session_id, "assistant", acc.text or "",
                tool_calls_json=json.dumps([tc.model_dump() for tc in calls]),
            )

            for idx, tc in enumerate(calls):
                remaining = [
                    {"tool_name": t.function.name, "arguments": t.function.arguments, "call_id": t.id}
                    for t in calls[idx + 1:]
                ]
                yield self._stream_event(
                    OrchestratorMessageType.TOOL_CALL, tool_name=tc.function.name,
                    arguments=tc.function.arguments, call_id=tc.id, session_id=session_id,
                )
                outcome = await self._process_single_call(
                    registry, tc.function.name, tc.function.arguments, tc.id,
                    session_id, remaining,
                )
                if outcome["action"] == "confirm":
                    async for event in self._emit_waiting_confirmation(outcome, session_id):
                        yield event
                    return
                if outcome["action"] == "executed":
                    result = outcome["result"]
                    all_results.append(result)
                    yield self._stream_event(
                        OrchestratorMessageType.TOOL_RESULT, tool_name=result.tool_name,
                        call_id=result.call_id, success=result.success, error=result.error,
                        data_preview=_preview_data(result.data), session_id=session_id,
                    )
                else:
                    yield self._stream_event(
                        OrchestratorMessageType.TOOL_RESULT, tool_name=tc.function.name,
                        call_id=tc.id, success=False, error=outcome["tool_msg"].content,
                        session_id=session_id,
                    )
                messages.append(outcome["tool_msg"])

        final_text = "I've reached the maximum number of tool call iterations. Please try a simpler request."
        await self._conversation.append_message(session_id, "assistant", final_text)
        yield self._stream_event(
            OrchestratorMessageType.DONE, session_id=session_id,
            response_text=final_text, iterations_used=iterations,
        )
