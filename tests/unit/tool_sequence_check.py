"""Structural validator for OpenAI-compatible tool-calling sequences.

Helper module (not a test file: no test_ prefix, never collected).
Enforces the real provider contract, which is structural — not "a call id
appeared somewhere before":

1. every tool result belongs to an existing tool_call;
2. the tool result comes AFTER the assistant message that created the call;
3. no assistant/user/system message may sit between an assistant(tool_calls)
   and its tool results (pending calls must be answered first);
4. every tool_call receives exactly one tool result (no duplicates, none missing);
5. (checked by callers via reload) a complete sequence stays valid after reload.

Set allow_pending=True only for in-flight states (e.g. waiting approval),
where calls were requested but results do not exist yet.
"""

from core.contracts.llm import LLMMessage


def assert_valid_tool_sequence(messages, *, allow_pending=False):
    """Validate a chronological list of LLMMessage objects. Raises AssertionError."""
    pending = {}  # call_id -> index of the assistant message that created it
    answered = set()
    for index, message in enumerate(messages):
        role = message.role
        if role == "assistant" and message.tool_calls:
            if pending:
                raise AssertionError(
                    f"message {index}: assistant(tool_calls) interrupts "
                    f"pending calls {sorted(pending)}"
                )
            for call in message.tool_calls:
                if call.id in answered:
                    raise AssertionError(f"message {index}: call id answered twice: {call.id}")
                if call.id in pending:  # pragma: no cover - defensive
                    raise AssertionError(f"message {index}: duplicate call id: {call.id}")
                pending[call.id] = index
        elif role == "tool":
            call_id = message.tool_call_id
            if not call_id:
                raise AssertionError(f"message {index}: tool message without tool_call_id")
            if call_id not in pending:
                raise AssertionError(
                    f"message {index}: orphan tool result for unknown call {call_id!r}"
                )
            answered.add(call_id)
            del pending[call_id]
        else:
            # user / system / plain assistant text: must not cut a sequence.
            if pending:
                raise AssertionError(
                    f"message {index}: {role} message interrupts "
                    f"pending calls {sorted(pending)}"
                )
    if not allow_pending and pending:
        raise AssertionError(f"unanswered tool calls at end of sequence: {sorted(pending)}")
