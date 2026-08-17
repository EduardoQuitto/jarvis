"""Controlled application launch and termination tools."""

import subprocess
import time
from typing import Any, Optional, Type
from pydantic import BaseModel, Field
import psutil

from core.contracts.enums import SecurityLevel
from core.contracts.tool import BaseTool, ToolResult
from security.allowlist import AllowlistValidator, SecurityValidationError


class LaunchAppArgs(BaseModel):
    app_name: str = Field(..., description="Approved application alias or executable name (e.g. 'notepad', 'calc', 'vscode')")


class LaunchApplicationTool(BaseTool):
    """Tool to safely launch approved applications from the allowlist."""

    name: str = "launch_application"
    description: str = "Launch an approved application defined in the security allowlist."
    security_level: SecurityLevel = SecurityLevel.YELLOW
    args_schema: Optional[Type[BaseModel]] = LaunchAppArgs

    def __init__(self, validator: Optional[AllowlistValidator] = None):
        self.validator = validator or AllowlistValidator()

    async def execute(self, **kwargs: Any) -> ToolResult:
        start = time.perf_counter()
        app_name = kwargs.get("app_name", "")
        try:
            exe_to_launch = self.validator.get_allowed_executable(app_name)
            process = subprocess.Popen([exe_to_launch], shell=False)
            duration_ms = (time.perf_counter() - start) * 1000.0
            return ToolResult.ok(
                data={"launched": True, "app_name": app_name, "executable": exe_to_launch, "pid": process.pid},
                security_level=self.security_level,
                execution_time_ms=duration_ms,
            )
        except SecurityValidationError as se:
            duration_ms = (time.perf_counter() - start) * 1000.0
            return ToolResult.fail(error=str(se), security_level=self.security_level, execution_time_ms=duration_ms)
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000.0
            return ToolResult.fail(error=f"Failed to launch '{app_name}': {str(e)}", security_level=self.security_level, execution_time_ms=duration_ms)


class CloseAppArgs(BaseModel):
    app_name: str = Field(..., description="Approved application alias to close")


class CloseApplicationTool(BaseTool):
    """Tool to safely close running instances of an approved application."""

    name: str = "close_application"
    description: str = "Close running instances of an approved application."
    security_level: SecurityLevel = SecurityLevel.YELLOW
    args_schema: Optional[Type[BaseModel]] = CloseAppArgs

    def __init__(self, validator: Optional[AllowlistValidator] = None):
        self.validator = validator or AllowlistValidator()

    async def execute(self, **kwargs: Any) -> ToolResult:
        start = time.perf_counter()
        app_name = kwargs.get("app_name", "")
        try:
            exe_name = self.validator.get_allowed_executable(app_name).lower()
            terminated = 0
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] and proc.info['name'].lower() == exe_name:
                        proc.terminate()
                        terminated += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            duration_ms = (time.perf_counter() - start) * 1000.0
            return ToolResult.ok(
                data={"closed": True, "app_name": app_name, "instances_terminated": terminated},
                security_level=self.security_level,
                execution_time_ms=duration_ms,
            )
        except SecurityValidationError as se:
            duration_ms = (time.perf_counter() - start) * 1000.0
            return ToolResult.fail(error=str(se), security_level=self.security_level, execution_time_ms=duration_ms)
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000.0
            return ToolResult.fail(error=f"Failed to close '{app_name}': {str(e)}", security_level=self.security_level, execution_time_ms=duration_ms)
