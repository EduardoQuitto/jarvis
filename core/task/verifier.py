"""Verification Engine — verifies task completion and builds evidence trails."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.contracts.enums import TaskStatus
from core.contracts.task import Task
from core.events.bus import get_event_bus
from core.events.models import EventType, SystemEvent
from core.logger import get_logger

logger = get_logger("jarvis.verifier")


class VerificationResult:
    """Result of a verification check."""

    def __init__(
        self,
        is_verified: bool,
        confidence: float,
        checks_passed: int,
        checks_total: int,
        evidence: List[Dict[str, Any]],
        notes: str = "",
    ):
        self.is_verified = is_verified
        self.confidence = confidence
        self.checks_passed = checks_passed
        self.checks_total = checks_total
        self.evidence = evidence
        self.notes = notes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_verified": self.is_verified,
            "confidence": self.confidence,
            "checks_passed": self.checks_passed,
            "checks_total": self.checks_total,
            "evidence": self.evidence,
            "notes": self.notes,
        }


class VerificationEngine:
    """Verifies task completion and builds evidence trails.

    Checks:
    - Objective was addressed
    - No errors occurred
    - Tool calls were successful
    - Expected outputs are present
    """

    def __init__(self):
        self._event_bus = get_event_bus()

    async def verify_task_completion(self, task: Task) -> VerificationResult:
        """Verify that a task has been completed successfully."""
        logger.info("Verifying task completion: %s", task.task_id)

        checks_passed = 0
        checks_total = 0
        evidence = []
        notes = []

        # Check 1: Status is COMPLETED
        checks_total += 1
        if task.status == TaskStatus.COMPLETED:
            checks_passed += 1
            evidence.append({"check": "status", "result": "COMPLETED"})
        else:
            evidence.append({"check": "status", "result": task.status.value})
            notes.append(f"Status is {task.status.value}, expected COMPLETED")

        # Check 2: Has a result
        checks_total += 1
        if task.result:
            checks_passed += 1
            evidence.append({"check": "result", "result": "present", "preview": task.result[:100]})
        else:
            evidence.append({"check": "result", "result": "missing"})
            notes.append("No result provided")

        # Check 3: No errors
        checks_total += 1
        errors = json.loads(task.errors) if isinstance(task.errors, str) and task.errors else (task.errors if task.errors else [])
        if not errors:
            checks_passed += 1
            evidence.append({"check": "errors", "result": "none"})
        else:
            evidence.append({"check": "errors", "result": f"{len(errors)} errors", "last": errors[-1] if errors else ""})
            notes.append(f"Task has {len(errors)} errors")

        # Check 4: Progress is 100%
        checks_total += 1
        if task.progress_pct >= 100.0:
            checks_passed += 1
            evidence.append({"check": "progress", "result": f"{task.progress_pct}%"})
        else:
            evidence.append({"check": "progress", "result": f"{task.progress_pct}%"})
            notes.append(f"Progress is {task.progress_pct}%, expected 100%")

        # Calculate confidence
        confidence = checks_passed / checks_total if checks_total > 0 else 0.0
        is_verified = confidence >= 0.75  # 75% threshold

        result = VerificationResult(
            is_verified=is_verified,
            confidence=confidence,
            checks_passed=checks_passed,
            checks_total=checks_total,
            evidence=evidence,
            notes="; ".join(notes) if notes else "All checks passed",
        )

        # Log verification
        await self._event_bus.publish(SystemEvent(
            event_type=EventType.TASK_COMPLETED if is_verified else EventType.TASK_FAILED,
            source="verifier",
            data={
                "task_id": task.task_id,
                "verified": is_verified,
                "confidence": confidence,
                "checks_passed": checks_passed,
                "checks_total": checks_total,
            },
        ))

        logger.info(
            "Verification for %s: %s (%.1f%% confidence, %d/%d checks)",
            task.task_id,
            "PASSED" if is_verified else "FAILED",
            confidence * 100,
            checks_passed,
            checks_total,
        )

        return result

    async def verify_tool_results(
        self,
        tool_results: List[Dict[str, Any]],
        expected_tools: Optional[List[str]] = None,
    ) -> VerificationResult:
        """Verify a set of tool execution results."""
        checks_passed = 0
        checks_total = 0
        evidence = []

        expected_set = set(expected_tools) if expected_tools else set()
        executed_set = set()

        for tr in tool_results:
            tool_name = tr.get("tool_name", "unknown")
            success = tr.get("success", False)
            checks_total += 1
            executed_set.add(tool_name)

            if success:
                checks_passed += 1
                evidence.append({"tool": tool_name, "result": "success"})
            else:
                evidence.append({"tool": tool_name, "result": "failed", "error": tr.get("error")})

        # Check all expected tools were executed
        if expected_tools:
            for expected in expected_set - executed_set:
                checks_total += 1
                evidence.append({"tool": expected, "result": "not_executed"})

        confidence = checks_passed / checks_total if checks_total > 0 else 1.0

        return VerificationResult(
            is_verified=confidence >= 0.8,
            confidence=confidence,
            checks_passed=checks_passed,
            checks_total=checks_total,
            evidence=evidence,
        )
