"""Application and process manager for the Windows Agent."""

import subprocess
from typing import Any, Dict, List, Optional
import psutil

from security.allowlist import AllowlistValidator, SecurityValidationError


class WindowsAppManager:
    """Manages launching, monitoring and closing approved applications."""

    def __init__(self, validator: Optional[AllowlistValidator] = None):
        self.validator = validator or AllowlistValidator()

    def launch(self, app_alias: str) -> Dict[str, Any]:
        """Launch an approved application by alias."""
        exe_name = self.validator.get_allowed_executable(app_alias)
        process = subprocess.Popen([exe_name], shell=False)
        return {
            "app_alias": app_alias,
            "executable": exe_name,
            "pid": process.pid,
            "status": "launched",
        }

    def close(self, app_alias: str) -> Dict[str, Any]:
        """Terminate running instances of an approved application."""
        exe_name = self.validator.get_allowed_executable(app_alias).lower()
        terminated_pids: List[int] = []

        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == exe_name:
                    proc.terminate()
                    terminated_pids.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return {
            "app_alias": app_alias,
            "executable": exe_name,
            "terminated_count": len(terminated_pids),
            "terminated_pids": terminated_pids,
        }

    def is_running(self, app_alias: str) -> bool:
        """Check if an approved application has active processes."""
        try:
            exe_name = self.validator.get_allowed_executable(app_alias).lower()
            for proc in psutil.process_iter(['name']):
                try:
                    if proc.info['name'] and proc.info['name'].lower() == exe_name:
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except SecurityValidationError:
            return False
        return False
