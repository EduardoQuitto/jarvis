"""Tests for file sandbox: prefix trick, traversal, symlink."""

import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from security.allowlist import AllowlistValidator, SecurityValidationError


class TestFileSandbox:
    """AllowlistValidator.validate_file_path blocks prefix tricks and traversal."""

    def test_valid_file_passes(self, tmp_path):
        target = tmp_path / "workspace" / "test.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("hello")

        with patch("security.allowlist.get_settings") as mock_settings:
            mock_settings.return_value.allowed_paths = [str(tmp_path / "workspace")]
            validator = AllowlistValidator()
            result = validator.validate_file_path(str(target), must_exist=False)
            assert result == target

    def test_prefix_trick_blocked(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside = tmp_path / "evil-workspace"
        outside.mkdir()

        malicious = str(outside) + str(workspace).replace("\\", "/").replace(":", "")  # path traversal

        with patch("security.allowlist.get_settings") as mock_settings:
            mock_settings.return_value.allowed_paths = [str(workspace)]
            validator = AllowlistValidator()
            # Try to access a file outside allowed paths using a crafted path
            with pytest.raises(SecurityValidationError):
                validator.validate_file_path(str(outside / "secret.txt"), must_exist=False)

    def test_dot_dot_traversal_blocked(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with patch("security.allowlist.get_settings") as mock_settings:
            mock_settings.return_value.allowed_paths = [str(workspace)]
            validator = AllowlistValidator()
            with pytest.raises(SecurityValidationError):
                validator.validate_file_path(str(workspace / ".." / ".." / "etc" / "passwd"), must_exist=False)

    def test_absolute_path_outside_blocked(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with patch("security.allowlist.get_settings") as mock_settings:
            mock_settings.return_value.allowed_paths = [str(workspace)]
            validator = AllowlistValidator()
            with pytest.raises(SecurityValidationError):
                validator.validate_file_path("/etc/passwd", must_exist=False)

    def test_symlink_outside_blocked(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        secret = tmp_path / "secret.txt"
        secret.write_text("secret")
        link = workspace / "link"
        os.symlink(str(secret), str(link))

        with patch("security.allowlist.get_settings") as mock_settings:
            mock_settings.return_value.allowed_paths = [str(workspace)]
            validator = AllowlistValidator()
            with pytest.raises(SecurityValidationError):
                validator.validate_file_path(str(link), must_exist=False)

    def test_symlink_inside_allowed(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        real = workspace / "real.txt"
        real.write_text("content")
        link = workspace / "link.txt"
        os.symlink(str(real), str(link))

        with patch("security.allowlist.get_settings") as mock_settings:
            mock_settings.return_value.allowed_paths = [str(workspace)]
            validator = AllowlistValidator()
            result = validator.validate_file_path(str(link), must_exist=False)
            assert result == link.resolve()
