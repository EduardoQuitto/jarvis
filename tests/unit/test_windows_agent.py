"""Unit tests for Windows Agent."""

import pytest
from windows_agent.system import WindowsSystemCollector
from windows_agent.manager import WindowsAppManager
from windows_agent.agent import WindowsAgent
from tools.registry import ToolRegistry


def test_windows_system_collector():
    metrics = WindowsSystemCollector.collect(node_id="test-win-node")
    assert metrics.node_id == "test-win-node"
    assert metrics.cpu.cores_logical >= 1
    assert metrics.memory.total_bytes > 0
    assert metrics.uptime_seconds >= 0.0


def test_windows_app_manager_validation():
    manager = WindowsAppManager()
    
    # Check running for valid app shouldn't raise exception
    is_notepad = manager.is_running("notepad")
    assert isinstance(is_notepad, bool)

    # Check invalid app should safely return False
    is_malicious = manager.is_running("unknown_malicious_app_123")
    assert is_malicious is False


def test_windows_agent_lifecycle():
    registry = ToolRegistry()
    agent = WindowsAgent(tool_registry=registry)
    
    assert agent.is_active is False
    
    agent.start()
    assert agent.is_active is True
    assert len(registry.list_tools()) > 0
    
    health = agent.get_health()
    assert health["status"] == "healthy"
    assert health["node_id"] == "node2-dev"
    assert health["registered_tools_count"] > 0
    assert "cpu" in health["system"]

    agent.stop()
    assert agent.is_active is False
