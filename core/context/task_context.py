"""Task Context — compact operational state representation for the LLM.

Uses the existing Task and TaskCheckpoint infrastructure to produce a
compact, structured summary of the current task state. This is an
operational representation, not a replacement for the persisted task.
"""

from typing import List, Optional

from core.contracts.task import Task, TaskCheckpoint
from core.logger import get_logger

logger = get_logger("jarvis.context.task")


class TaskContextBuilder:
    """Builds a compact task state string for inclusion in the LLM context.

    The output is deterministic and structured:

        TASK
        <objective>

        CURRENT STATE
        <current step or status>

        PROGRESS
        <completed_steps>/<total_steps>

        IMPORTANT DECISIONS
        <decisions from task context>

        KNOWN ISSUES
        <errors accumulated>

        NEXT STEP
        <next step from checkpoints>
    """

    def build(
        self,
        task: Optional[Task],
        checkpoints: Optional[List[TaskCheckpoint]] = None,
    ) -> Optional[str]:
        """Build compact task context. Returns None if no task."""
        if task is None:
            return None

        sections: List[str] = []

        sections.append(f"TASK\n{task.objective[:200]}")

        current_state = task.current_step or task.status.value
        sections.append(f"CURRENT STATE\n{current_state}")

        if task.total_steps > 0:
            sections.append(f"PROGRESS\n{task.completed_steps}/{task.total_steps} steps completed")

        decisions = self._extract_decisions(task)
        if decisions:
            sections.append(f"IMPORTANT DECISIONS\n{', '.join(d[:100] for d in decisions)}")

        if task.errors:
            sections.append(f"KNOWN ISSUES\n{'; '.join(e[:100] for e in task.errors[:5])}")

        next_step = self._find_next_step(checkpoints or [])
        if next_step:
            sections.append(f"NEXT STEP\n{next_step[:200]}")

        return "\n\n".join(sections)

    def _extract_decisions(self, task: Task) -> List[str]:
        """Extract important decisions from task context."""
        decisions = []
        context = task.context or {}
        decision_keys = ["decisions", "tech_stack", "architecture", "approach"]
        for key in decision_keys:
            value = context.get(key)
            if isinstance(value, list):
                decisions.extend(str(v) for v in value[:5])
            elif isinstance(value, str) and value:
                decisions.append(value)
        return decisions

    def _find_next_step(self, checkpoints: List[TaskCheckpoint]) -> Optional[str]:
        """Find the next pending step from checkpoints."""
        for cp in checkpoints:
            if cp.status.value == "PENDING" and cp.step_description:
                return cp.step_description
        return None
