"""JARVIS Core network bridge (CORE -> SERVER)."""

from core.network.node_client import RemoteNodeClient, RemoteNodeError
from core.network.node_presence import NodePresenceManager, project_version
from core.network.task_client import DistributedTaskClient, dict_to_task

__all__ = [
    "RemoteNodeClient",
    "RemoteNodeError",
    "NodePresenceManager",
    "project_version",
    "DistributedTaskClient",
    "dict_to_task",
]
