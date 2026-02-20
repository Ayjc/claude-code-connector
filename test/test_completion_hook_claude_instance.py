from __future__ import annotations

import importlib.util
import json
from importlib.machinery import SourceFileLoader
from pathlib import Path


def _load_hook_module() -> object:
    repo_root = Path(__file__).resolve().parents[1]
    hook_path = repo_root / "bin" / "ccb-completion-hook"
    loader = SourceFileLoader("ccb_completion_hook_claude", str(hook_path))
    spec = importlib.util.spec_from_loader("ccb_completion_hook_claude", loader)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_completion_hook_routes_to_specific_claude_instance(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """When caller=claude with instance=2, hook should select instance 2's pane."""
    hook = _load_hook_module()

    cfg = tmp_path / ".ccb"
    cfg.mkdir(parents=True, exist_ok=True)
    session_file = cfg / ".claude-session"
    session_file.write_text(
        json.dumps(
            {
                "provider": "claude",
                "work_dir": str(tmp_path),
                "instances": {
                    "1": {
                        "instance": "1",
                        "terminal": "tmux",
                        "pane_id": "%10",
                        "pane_title_marker": "CCB-Claude#1",
                        "work_dir": str(tmp_path),
                        "active": True,
                    },
                    "2": {
                        "instance": "2",
                        "terminal": "tmux",
                        "pane_id": "%11",
                        "pane_title_marker": "CCB-Claude#2",
                        "work_dir": str(tmp_path),
                        "active": True,
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    captured: dict[str, str] = {}

    def _fake_send_via_terminal(pane_id: str, message: str, terminal: str, session_data: dict) -> bool:
        captured["pane_id"] = pane_id
        captured["terminal"] = terminal
        captured["message"] = message
        return True

    monkeypatch.setattr(hook, "send_via_terminal", _fake_send_via_terminal)
    monkeypatch.setenv("CCB_COMPLETION_HOOK_ENABLED", "1")
    monkeypatch.setenv("CCB_CALLER", "claude")
    monkeypatch.setenv("CCB_CALLER_INSTANCE", "2")
    monkeypatch.setenv("CCB_WORK_DIR", str(tmp_path))
    monkeypatch.setattr(hook.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        hook.sys,
        "argv",
        ["ccb-completion-hook", "--provider", "gemini", "--reply", "done", "--req-id", "r1"],
    )

    rc = hook.main()
    assert rc == 0
    assert captured["pane_id"] == "%11"
    assert captured["terminal"] == "tmux"
    assert "CCB_TASK_COMPLETED" in captured["message"]


def test_completion_hook_ambiguous_claude_instances(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """When caller=claude with multiple instances but no caller_instance, should be ambiguous."""
    hook = _load_hook_module()

    cfg = tmp_path / ".ccb"
    cfg.mkdir(parents=True, exist_ok=True)
    session_file = cfg / ".claude-session"
    session_file.write_text(
        json.dumps(
            {
                "provider": "claude",
                "work_dir": str(tmp_path),
                "instances": {
                    "1": {
                        "instance": "1",
                        "terminal": "tmux",
                        "pane_id": "%10",
                        "work_dir": str(tmp_path),
                        "active": True,
                    },
                    "2": {
                        "instance": "2",
                        "terminal": "tmux",
                        "pane_id": "%11",
                        "work_dir": str(tmp_path),
                        "active": True,
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Track if ask command fallback is attempted
    ask_attempted: dict[str, object] = {}

    def _fake_find_ask_command() -> str | None:
        ask_attempted["called"] = True
        return None  # Return None so hook exits cleanly

    monkeypatch.setattr(hook, "find_ask_command", _fake_find_ask_command)
    monkeypatch.setenv("CCB_COMPLETION_HOOK_ENABLED", "1")
    monkeypatch.setenv("CCB_CALLER", "claude")
    monkeypatch.delenv("CCB_CALLER_INSTANCE", raising=False)
    monkeypatch.setenv("CCB_WORK_DIR", str(tmp_path))
    monkeypatch.setattr(hook.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        hook.sys,
        "argv",
        ["ccb-completion-hook", "--provider", "gemini", "--reply", "done", "--req-id", "r1"],
    )

    rc = hook.main()
    # Should fall through to ask fallback since pane_id couldn't be resolved
    assert rc == 0
    assert ask_attempted.get("called") is True


def test_completion_hook_fallback_ask_includes_claude_instance(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """When caller=claude with instance, fallback ask args should include --instance."""
    hook = _load_hook_module()

    # No session file at all - force fallback to ask command
    monkeypatch.setenv("CCB_COMPLETION_HOOK_ENABLED", "1")
    monkeypatch.setenv("CCB_CALLER", "claude")
    monkeypatch.setenv("CCB_CALLER_INSTANCE", "2")
    monkeypatch.setenv("CCB_WORK_DIR", str(tmp_path))
    monkeypatch.setattr(hook.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        hook.sys,
        "argv",
        ["ccb-completion-hook", "--provider", "gemini", "--reply", "done", "--req-id", "r1"],
    )

    captured_args: dict[str, list[str]] = {}

    def _fake_find_ask_command() -> str:
        return "/usr/local/bin/ask"

    import subprocess as _subprocess

    original_run = _subprocess.run

    def _fake_run(cmd, **kwargs):
        captured_args["cmd"] = list(cmd)
        # Return a fake result
        class FakeResult:
            returncode = 0
        return FakeResult()

    monkeypatch.setattr(hook, "find_ask_command", _fake_find_ask_command)
    monkeypatch.setattr(hook.subprocess, "run", _fake_run)

    rc = hook.main()
    assert rc == 0
    assert "--instance" in captured_args.get("cmd", [])
    instance_idx = captured_args["cmd"].index("--instance")
    assert captured_args["cmd"][instance_idx + 1] == "2"
