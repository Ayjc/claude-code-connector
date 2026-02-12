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


def test_default_caller_prefers_claude_in_claudecode_env(monkeypatch) -> None:
    ask = _load_ask_module()
    monkeypatch.delenv("CCB_CALLER", raising=False)
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CCB_MANAGED", "1")
    monkeypatch.setenv("CODEX_SESSION_ID", "ai-123")
    monkeypatch.setenv("CODEX_RUNTIME_DIR", "/tmp/codex-runtime")
    monkeypatch.setenv("CODEX_TMUX_SESSION", "%2")
    monkeypatch.setenv("TMUX_PANE", "%1")

    assert ask._default_caller() == "claude"


def test_default_caller_detects_codex_from_current_pane(monkeypatch) -> None:
    ask = _load_ask_module()
    monkeypatch.delenv("CCB_CALLER", raising=False)
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.setenv("CCB_MANAGED", "1")
    monkeypatch.setenv("CODEX_SESSION_ID", "ai-123")
    monkeypatch.setenv("CODEX_TMUX_SESSION", "%9")
    monkeypatch.setenv("TMUX_PANE", "%9")

    assert ask._default_caller() == "codex"


def test_default_caller_respects_explicit_env_override(monkeypatch) -> None:
    ask = _load_ask_module()
    monkeypatch.setenv("CCB_CALLER", "claude")
    monkeypatch.setenv("CODEX_SESSION_ID", "ai-123")

    assert ask._default_caller() == "claude"
