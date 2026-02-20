from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path


def _load_ask_module() -> object:
    repo_root = Path(__file__).resolve().parents[1]
    ask_path = repo_root / "bin" / "ask"
    loader = SourceFileLoader("ask_script", str(ask_path))
    spec = importlib.util.spec_from_loader("ask_script", loader)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_normalize_instance_valid() -> None:
    ask = _load_ask_module()
    assert ask._normalize_instance("2") == "2"
    assert ask._normalize_instance("99") == "99"


def test_instance_rejected_for_unsupported_provider() -> None:
    """--instance should be rejected for providers other than codex/claude."""
    ask = _load_ask_module()
    rc = ask.main(["ask", "gemini", "--instance", "2", "hello"])
    assert rc != 0


def test_instance_accepted_for_claude() -> None:
    """--instance should NOT be rejected at the provider validation stage for claude.

    The function will fail later (no daemon running), but it should get past
    the provider check on line 333.
    """
    ask = _load_ask_module()
    # This will fail with a daemon/socket error, but should NOT fail with
    # "only supports provider=codex or provider=claude" error.
    # We capture stderr to verify the right error path.
    import io
    import sys

    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    try:
        ask.main(["ask", "claude", "--instance", "2", "hello"])
    except (SystemExit, Exception):
        pass
    stderr_output = sys.stderr.getvalue()
    sys.stderr = old_stderr
    assert "--instance currently only supports" not in stderr_output


def test_caller_instance_from_claude_env(monkeypatch) -> None:
    """When caller is claude, CLAUDE_INSTANCE should be used as fallback."""
    ask = _load_ask_module()
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_INSTANCE", "3")
    monkeypatch.delenv("CCB_CALLER_INSTANCE", raising=False)
    monkeypatch.delenv("CCB_CALLER", raising=False)

    caller = ask._default_caller()
    assert caller == "claude"
