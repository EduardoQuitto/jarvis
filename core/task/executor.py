"""Task Executor — runs task steps through the agentic loop with retry logic."""

import json
from typing import Any, Dict, List, Optional

from core.contracts.enums import TaskStatus
from core.contracts.task import Task
from core.orchestrator.engine import Orchestrator
from core.orchestrator.tool_executor import ToolExecutor
from core.events.bus import get_event_bus
from core.events.models import EventType, SystemEvent
from core.logger import get_logger

logger = get_logger("jarvis.step_executor")


class StepExecutor:
    """Executes tasks by breaking objectives into tool-based steps.

    Uses the Orchestrator for LLM interaction and ToolExecutor for direct tool calls.
    Handles retry logic, progress tracking, and error recovery.
    """

    def __init__(
        self,
        orchestrator: Optional[Orchestrator] = None,
        tool_executor: Optional[ToolExecutor] = None,
    ):
        self._orchestrator = orchestrator
        self._tool_executor = tool_executor or ToolExecutor()
        self._event_bus = get_event_bus()

    def _get_orchestrator(self) -> Orchestrator:
        if self._orchestrator is None:
            raise RuntimeError("Orchestrator not initialized for StepExecutor")
        return self._orchestrator

    async def execute_task(self, task: Task) -> str:
        """Execute a task through the agentic loop.

        Returns the final result string.
        """
        logger.info("Executing task %s: %s", task.task_id, task.objective[:60])

        await self._event_bus.publish(SystemEvent(
            event_type=EventType.TASK_STARTED,
            source="step_executor",
            data={"task_id": task.task_id},
        ))

        try:
            # Use orchestrator to process the objective as a message
            from core.contracts.orchestrator import OrchestratorRequest
            request = OrchestratorRequest(
                message=task.objective,
                session_id=task.conversation_id,
                device_id=task.device_id or "system",
            )

            result = await self._get_orchestrator().process_message(request)

            # Track progress
            if task.total_steps > 0:
                task.completed_steps += 1
                task.progress_pct = (task.completed_steps / task.total_steps) * 100

            return result.response_text

        except Exception as e:
            logger.error("Task %s failed: %s", task.task_id, str(e))
            raise

    async def execute_single_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        task_id: Optional[str] = None,
    ) -> Any:
        """Execute a single tool call directly, bypassing the LLM loop.

        Useful for known, deterministic steps.
        """
        logger.info("Direct tool execution: %s(%s)", tool_name, json.dumps(arguments)[:100])

        await self._event_bus.publish(SystemEvent(
            event_type=EventType.TOOL_CALL,
            source="step_executor",
            data={"tool_name": tool_name, "arguments": arguments, "task_id": task_id},
        ))

        result = await self._tool_executor.execute_tool_call(
            tool_name=tool_name,
            arguments=arguments,
        )

        await self._event_bus.publish(SystemEvent(
            event_type=EventType.TOOL_RESULT,
            source="step_executor",
            data={
                "tool_name": tool_name,
                "success": result.success,
                "task_id": task_id,
            },
        ))

        return result

    async def execute_with_retry(
        self,
        task: Task,
        max_retries: int = 2,
    ) -> str:
        """Execute a task with automatic retry on failure."""
        retries = 0
        last_error = ""

        while retries <= max_retries:
            try:
                result = await self.execute_task(task)
                return result
            except Exception as e:
                last_error = str(e)
                retries += 1
                logger.warning(
                    "Task %s attempt %d/%d failed: %s",
                    task.task_id,
                    retries,
                    max_retries + 1,
                    last_error,
                )
                if retries <= max_retries:
                    # Add checkpoint for retry
                    await self._event_bus.publish(SystemEvent(
                        event_type=EventType.TASK_FAILED,
                        source="step_executor",
                        data={
                            "task_id": task.task_id,
                            "error": last_error,
                            "retry": retries,
                            "max_retries": max_retries,
                        },
                    ))

        raise RuntimeError(f"Task {task.task_id} failed after {max_retries} retries: {last_error}")
