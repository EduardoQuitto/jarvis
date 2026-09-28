"""Unit tests for filesystem analysis + security tools (Phase 15.1).

File tests run inside tmp_path with a patched allowlist (same pattern as
the file-tool tests). Symlink cases skip cleanly without OS privilege.
"""

import hashlib
import os

import pytest
from unittest.mock import patch

from tools.registry import ToolRegistry
from tools.builtin.filesystem_analysis_tool import FindDuplicatesTool, DiskUsageAnalysisTool
from tools.builtin.security_tool import GeneratePasswordTool, HashFileTool, VerifyChecksumTool


def _sandboxed_registry(tmp_path):
    from types import SimpleNamespace

    patcher = patch(
        "security.allowlist.get_settings",
        return_value=SimpleNamespace(allowed_apps={}, allowed_paths=[str(tmp_path)]),
    )
    patcher.start()
    registry = ToolRegistry()
    registry.register(FindDuplicatesTool())
    registry.register(DiskUsageAnalysisTool())
    registry.register(GeneratePasswordTool())
    registry.register(HashFileTool())
    registry.register(VerifyChecksumTool())
    return registry, patcher


@pytest.fixture
def sandbox():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        from pathlib import Path

        path = Path(tmp)
        registry, patcher = _sandboxed_registry(path)
        try:
            yield path, registry
        finally:
            patcher.stop()


def _can_symlink(tmp_path):
    probe_src = tmp_path / "probe_src"
    probe_src.write_text("x")
    try:
        os.symlink(str(probe_src), str(tmp_path / "probe_link"))
    except OSError:
        return False
    return True


# --- find_duplicates ---

@pytest.mark.asyncio
async def test_find_duplicates_simple(sandbox):
    tmp_path, registry = sandbox
    (tmp_path / "a.txt").write_text("same content here")
    (tmp_path / "b.txt").write_text("same content here")
    (tmp_path / "unique.txt").write_text("something else entirely!!")

    result = await registry.execute_tool(
        "find_duplicates", {"directory": str(tmp_path)}, confirmed=True, source="operator",
    )
    assert result.success is True
    assert result.data["duplicate_groups"] == 1
    group = result.data["duplicates"][0]
    assert group["size_bytes"] == len("same content here")
    assert sorted(group["files"]) == sorted([str(tmp_path / "a.txt"), str(tmp_path / "b.txt")])
    assert result.data["files_scanned"] == 3


@pytest.mark.asyncio
async def test_same_size_different_content_not_duplicates(sandbox):
    tmp_path, registry = sandbox
    (tmp_path / "a.bin").write_bytes(b"ABCD")
    (tmp_path / "b.bin").write_bytes(b"WXYZ")

    result = await registry.execute_tool(
        "find_duplicates", {"directory": str(tmp_path)}, confirmed=True, source="operator",
    )
    assert result.success is True
    assert result.data["duplicate_groups"] == 0


@pytest.mark.asyncio
async def test_broken_symlink_counted_as_skipped(sandbox):
    tmp_path, registry = sandbox
    if not _can_symlink(tmp_path):
        pytest.skip("OS blocks symlink creation here")
    (tmp_path / "real.txt").write_text("data!")
    os.symlink(str(tmp_path / "missing.txt"), str(tmp_path / "broken.txt"))

    result = await registry.execute_tool(
        "find_duplicates", {"directory": str(tmp_path)}, confirmed=True, source="operator",
    )
    assert result.success is True
    assert result.data["skipped"] >= 1


@pytest.mark.asyncio
async def test_symlink_outside_sandbox_skipped(sandbox):
    tmp_path, registry = sandbox
    if not _can_symlink(tmp_path):
        pytest.skip("OS blocks symlink creation here")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret-outside!!")
    inside_dir = tmp_path / "inside"
    inside_dir.mkdir()
    os.symlink(str(outside), str(inside_dir / "link.txt"))
    (inside_dir / "own.txt").write_text("secret-outside!!")

    result = await registry.execute_tool(
        "find_duplicates", {"directory": str(inside_dir)}, confirmed=True, source="operator",
    )
    assert result.success is True
    # own.txt must NOT match outside.txt: the escape was skipped
    assert result.data["duplicate_groups"] == 0
    assert result.data["skipped"] >= 1


@pytest.mark.asyncio
async def test_invalid_directory_and_sandbox_denial(sandbox):
    tmp_path, registry = sandbox
    missing = await registry.execute_tool(
        "find_duplicates", {"directory": str(tmp_path / "nope")}, confirmed=True, source="operator",
    )
    assert missing.success is False

    outside = await registry.execute_tool(
        "find_duplicates", {"directory": "/etc"}, confirmed=True, source="operator",
    )
    assert outside.success is False
    # Denied at the policy boundary (PATH containment) before execution.
    assert "Policy Denied" in (outside.error or "")

    traversal = await registry.execute_tool(
        "find_duplicates", {"directory": str(tmp_path / ".." / ".." / "etc")},
        confirmed=True, source="operator",
    )
    assert traversal.success is False


# --- disk_usage_analysis ---

@pytest.mark.asyncio
async def test_disk_usage_totals_and_tops(sandbox):
    tmp_path, registry = sandbox
    (tmp_path / "a.txt").write_bytes(b"x" * 100)
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_bytes(b"y" * 300)
    (sub / "c.txt").write_bytes(b"z" * 50)

    result = await registry.execute_tool(
        "disk_usage_analysis", {"path": str(tmp_path), "top_n": 2},
        confirmed=True, source="operator",
    )
    assert result.success is True
    data = result.data
    assert data["total_size_bytes"] == 450
    assert data["files"] == 3
    assert data["directories"] >= 2
    assert data["top_files"][0] == {"path": str(sub / "b.txt"), "size_bytes": 300}
    assert len(data["top_files"]) == 2
    assert data["top_directories"][0]["path"] == str(sub)


@pytest.mark.asyncio
async def test_disk_usage_respects_max_depth(sandbox):
    tmp_path, registry = sandbox
    deep = tmp_path / "l1" / "l2" / "l3"
    deep.mkdir(parents=True)
    (deep / "deep.txt").write_bytes(b"d" * 10)
    (tmp_path / "top.txt").write_bytes(b"t" * 10)

    shallow = await registry.execute_tool(
        "disk_usage_analysis", {"path": str(tmp_path), "max_depth": 1},
        confirmed=True, source="operator",
    )
    assert shallow.success is True
    assert shallow.data["total_size_bytes"] == 10

    full = await registry.execute_tool(
        "disk_usage_analysis", {"path": str(tmp_path), "max_depth": 10},
        confirmed=True, source="operator",
    )
    assert full.data["total_size_bytes"] == 20


@pytest.mark.asyncio
async def test_disk_usage_max_entries_caps_output(sandbox):
    tmp_path, registry = sandbox
    for i in range(10):
        (tmp_path / f"f{i}.txt").write_bytes(b"q")

    result = await registry.execute_tool(
        "disk_usage_analysis", {"path": str(tmp_path), "max_entries": 3, "top_n": 50},
        confirmed=True, source="operator",
    )
    assert result.success is True
    assert result.data["files"] == 3
    assert result.data["skipped"] >= 7


# --- generate_password ---

@pytest.mark.asyncio
async def test_password_lengths_and_classes(sandbox):
    _, registry = sandbox
    for length in (8, 16, 32):
        result = await registry.execute_tool(
            "generate_password", {"length": length, "complexity": "high"}, source="orchestrator",
        )
        assert result.success is True
        password = result.data["password"]
        assert len(password) == length
        assert any(c.islower() for c in password)
        assert any(c.isupper() for c in password)
        assert any(c.isdigit() for c in password)
        assert any(not c.isalnum() for c in password)

    medium = await registry.execute_tool(
        "generate_password", {"length": 12, "complexity": "medium"}, source="orchestrator",
    )
    assert medium.success is True
    assert any(c.isupper() for c in medium.data["password"])

    first = await registry.execute_tool(
        "generate_password", {"length": 16, "complexity": "high"}, source="orchestrator",
    )
    second = await registry.execute_tool(
        "generate_password", {"length": 16, "complexity": "high"}, source="orchestrator",
    )
    assert first.data["password"] != second.data["password"]


@pytest.mark.asyncio
async def test_password_invalid_parameters(sandbox):
    _, registry = sandbox
    for params in ({"length": 4}, {"length": 500}, {"length": "x"},
                   {"length": 16, "complexity": "extreme"}):
        result = await registry.execute_tool(
            "generate_password", params, source="orchestrator",
        )
        assert result.success is False


# --- hash_file / verify_checksum ---

@pytest.mark.asyncio
async def test_hash_known_vectors(sandbox):
    tmp_path, registry = sandbox
    target = tmp_path / "abc.txt"
    target.write_bytes(b"abc")

    sha256 = await registry.execute_tool(
        "hash_file", {"file_path": str(target), "algorithm": "sha256"}, source="orchestrator",
    )
    assert sha256.success is True
    assert sha256.data["hash_hex"] == hashlib.sha256(b"abc").hexdigest()
    assert sha256.data["hash_hex"] == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert sha256.data["size_bytes"] == 3

    md5 = await registry.execute_tool(
        "hash_file", {"file_path": str(target), "algorithm": "md5"}, source="orchestrator",
    )
    assert md5.data["hash_hex"] == "900150983cd24fb0d6963f7d28e17f72"


@pytest.mark.asyncio
async def test_hash_sha512_consistent(sandbox):
    tmp_path, registry = sandbox
    target = tmp_path / "data.bin"
    target.write_bytes(b"jarvis" * 1000)
    first = await registry.execute_tool(
        "hash_file", {"file_path": str(target), "algorithm": "sha512"}, source="orchestrator",
    )
    second = await registry.execute_tool(
        "hash_file", {"file_path": str(target), "algorithm": "sha512"}, source="orchestrator",
    )
    assert first.success and second.success
    assert len(first.data["hash_hex"]) == 128
    assert first.data["hash_hex"] == second.data["hash_hex"] == hashlib.sha512(b"jarvis" * 1000).hexdigest()


@pytest.mark.asyncio
async def test_hash_invalid_algorithm_and_missing_file(sandbox):
    tmp_path, registry = sandbox
    bad_algo = await registry.execute_tool(
        "hash_file", {"file_path": str(tmp_path / "x"), "algorithm": "rot13"},
        source="orchestrator",
    )
    assert bad_algo.success is False
    assert "Invalid algorithm" in (bad_algo.error or "")

    missing = await registry.execute_tool(
        "hash_file", {"file_path": str(tmp_path / "nope.txt")}, source="orchestrator",
    )
    assert missing.success is False


@pytest.mark.asyncio
async def test_verify_checksum_match_and_mismatch(sandbox):
    tmp_path, registry = sandbox
    target = tmp_path / "doc.txt"
    target.write_bytes(b"important-data")
    digest = hashlib.sha256(b"important-data").hexdigest()

    match = await registry.execute_tool(
        "verify_checksum",
        {"file_path": str(target), "expected_hash": digest, "algorithm": "sha256"},
        source="orchestrator",
    )
    assert match.success is True
    assert match.data["matches"] is True
    assert match.data["algorithm"] == "sha256"
    assert match.data["actual_hash"] == digest

    mismatch = await registry.execute_tool(
        "verify_checksum",
        {"file_path": str(target), "expected_hash": "0" * 64, "algorithm": "sha256"},
        source="orchestrator",
    )
    assert mismatch.success is True
    assert mismatch.data["matches"] is False

    auto = await registry.execute_tool(
        "verify_checksum",
        {"file_path": str(target), "expected_hash": digest.upper(), "algorithm": "auto"},
        source="orchestrator",
    )
    assert auto.success is True
    assert auto.data["algorithm"] == "sha256"
    assert auto.data["matches"] is True
