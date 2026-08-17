"""Command Line Interface for managing and testing JARVIS nodes."""

import argparse
import asyncio
import json
import sys
import uvicorn

from core.config import get_settings
from core.logger import configure_logging, get_logger
from core.planner.builder import PlanBuilder
from core.planner.engine import PlanExecutor
from memory.sqlite_provider import SQLiteMemoryProvider
from tools.registry import get_tool_registry
from tools import register_default_tools
from windows_agent.agent import WindowsAgent
from windows_agent.system import WindowsSystemCollector

logger = get_logger("jarvis.cli")


async def show_status():
    """Print local node health and telemetry."""
    settings = get_settings()
    registry = get_tool_registry()
    register_default_tools(registry)

    metrics = WindowsSystemCollector.collect(node_id=settings.node_id)
    gpu = WindowsSystemCollector.get_gpu_info()

    print("\n" + "=" * 60)
    print(f" J.A.R.V.I.S. Node Status [{settings.node_id} - {settings.node_role.value}]")
    print("=" * 60)
    print(f"OS:            {metrics.os_name} {metrics.os_version}")
    print(f"Uptime:        {metrics.uptime_seconds:.1f}s")
    print(f"CPU Usage:     {metrics.cpu.usage_percent:.1f}% ({metrics.cpu.cores_logical} logical cores)")
    print(f"RAM Usage:     {metrics.memory.usage_percent:.1f}% ({metrics.memory.used_bytes / (1024**3):.2f} GB / {metrics.memory.total_bytes / (1024**3):.2f} GB)")
    if gpu:
        print(f"GPU:           {gpu['name']} ({gpu['utilization_percent']}% util, {gpu['temperature_celsius']}°C)")
    else:
        print("GPU:           No dedicated NVIDIA GPU telemetry found")
    print(f"Registered Tools ({len(registry.list_tools())}):")
    for t in registry.list_tools():
        print(f"  • {t.name:<25} [{t.security_level.value}] — {t.description}")
    print("=" * 60 + "\n")


async def run_sample_plan():
    """Execute a sample deterministic multi-step plan."""
    settings = get_settings()
    registry = get_tool_registry()
    register_default_tools(registry)
    memory = SQLiteMemoryProvider()
    await memory.initialize()

    builder = PlanBuilder(goal="Diagnostic Health Check & Echo Ping")
    builder.add_step("s1", "get_system_metrics", description="Collect hardware metrics")
    builder.add_step("s2", "echo", parameters={"message": "Diagnostics Complete"}, description="Signal completion", depends_on=["s1"])

    plan = builder.build()
    executor = PlanExecutor(tool_registry=registry, memory_provider=memory)

    print(f"Executing plan: {plan.goal} (ID: {plan.plan_id})...")
    result = await executor.execute_plan(plan)
    print(f"Plan status: {result.status.value} in {result.total_duration_ms:.2f}ms")
    print(f"Steps executed: {result.steps_executed}")
    await memory.close()


def run_server():
    """Launch the FastAPI server using Uvicorn."""
    settings = get_settings()
    print(f"Starting JARVIS Server on http://{settings.host}:{settings.port}...")
    uvicorn.run("server.app:create_app", host=settings.host, port=settings.port, reload=settings.debug, factory=True)


def main():
    """Main CLI entrypoint."""
    configure_logging()
    parser = argparse.ArgumentParser(description="J.A.R.V.I.S. Command Line Interface")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Status command
    subparsers.add_parser("status", help="Display local node status and metrics")

    # Tools command
    subparsers.add_parser("tools", help="List registered tools and schemas")

    # Run Server command
    subparsers.add_parser("server", help="Start the FastAPI HTTP/WS node server")

    # Test Plan command
    subparsers.add_parser("test-plan", help="Run a diagnostic sample plan")

    args = parser.parse_args()

    if args.command == "status":
        asyncio.run(show_status())
    elif args.command == "tools":
        registry = get_tool_registry()
        register_default_tools(registry)
        for t in registry.list_tools():
            print(f"{t.name:<25} [{t.security_level.value}] {t.description}")
    elif args.command == "server":
        run_server()
    elif args.command == "test-plan":
        asyncio.run(run_sample_plan())
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
