"""Tests for Task Context builder (Phase 15.2)."""

import pytest
from datetime import datetime, timezone

from core.context.task_context import TaskContextBuilder
from core.contracts.task import Task, TaskCheckpoint
from core.contracts.enums import TaskStatus


class TestTaskContextBuilder:
    def test_no_task_returns_none(self):
        builder = TaskContextBuilder()
        assert builder.build(None) is None

    def test_basic_task(self):
        builder = TaskContextBuilder()
        task = Task(
            task_id="task-1",
            objective="Build a web app",
            status=TaskStatus.RUNNING,
            current_step="Implementing auth",
            total_steps=5,
            completed_steps=2,
        )
        result = builder.build(task)
        assert result is not None
        assert "Build a web app" in result
        assert "Implementing auth" in result
        assert "2/5" in result

    def test_task_with_decisions(self):
        builder = TaskContextBuilder()
        task = Task(
            task_id="task-2",
            objective="Refactor module",
            context={"decisions": ["FastAPI", "SQLite", "JWT"]},
            status=TaskStatus.RUNNING,
        )
        result = builder.build(task)
        assert "FastAPI" in result
        assert "SQLite" in result
        assert "JWT" in result

    def test_task_with_errors(self):
        builder = TaskContextBuilder()
        task = Task(
            task_id="task-3",
            objective="Deploy app",
            status=TaskStatus.FAILED,
            errors=["Connection timeout", "Build failed"],
        )
        result = builder.build(task)
        assert "Connection timeout" in result
        assert "Build failed" in result

    def test_task_with_checkpoints(self):
        builder = TaskContextBuilder()
        task = Task(
            task_id="task-4",
            objective="Migrate database",
            status=TaskStatus.RUNNING,
            total_steps=3,
            completed_steps=1,
        )
        checkpoints = [
            TaskCheckpoint(task_id="task-4", step_id="step-1", step_description="Create schema", status=TaskStatus.COMPLETED),
            TaskCheckpoint(task_id="task-4", step_id="step-2", step_description="Migrate data", status=TaskStatus.PENDING),
        ]
        result = builder.build(task, checkpoints)
        assert "Migrate data" in result

    def test_task_no_progress_when_zero_steps(self):
        builder = TaskContextBuilder()
        task = Task(
            task_id="task-5",
            objective="Simple task",
            status=TaskStatus.PENDING,
        )
        result = builder.build(task)
        assert "PROGRESS" not in result

    def test_task_context_is_compact(self):
        builder = TaskContextBuilder()
        task = Task(
            task_id="task-6",
            objective="A" * 500,
            context={"decisions": ["X" * 200, "Y" * 200, "Z" * 200]},
            status=TaskStatus.RUNNING,
            errors=["E" * 200],
        )
        result = builder.build(task)
        assert len(result) < 1000
