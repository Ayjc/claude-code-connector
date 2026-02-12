from __future__ import annotations

import importlib.util
import json
import os
from importlib.machinery import SourceFileLoader
from pathlib import Path


def _load_hook_module() -> object:
    repo_root = Path(__file__).resolve().parents[1]
    hook_path = repo_root / "bin" / "ccb-completion-hook"
    loader = SourceFileLoader("ccb_completion_hook_multi", str(hook_path))
    spec = importlib.util.spec_from_loader("ccb_completion_hook_multi", loader)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_completion_hook_routes_to_specific_codex_instance(
    monkeypatch,
    tmp_path: Path,
) -> None:
    hook = _load_hook_module()

    cfg = tmp_path / ".ccb"
    cfg.mkdir(parents=True, exist_ok=True)
    session_file = cfg / ".codex-session"
    session_file.write_text(
        json.dumps(
            {
                "provider": "codex",
                "work_dir": str(tmp_path),
                "instances": {
                    "1": {
                        "instance": "1",
                        "terminal": "tmux",
                        "pane_id": "%1",
                        "pane_title_marker": "CCB-Codex#1",
                        "work_dir": str(tmp_path),
                        "active": True,
                    },
                    "2": {
                        "instance": "2",
                        "terminal": "tmux",
                        "pane_id": "%2",
                        "pane_title_marker": "CCB-Codex#2",
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
    monkeypatch.setenv("CCB_CALLER", "codex")
    monkeypatch.setenv("CCB_CALLER_INSTANCE", "2")
    monkeypatch.setenv("CCB_WORK_DIR", str(tmp_path))
    monkeypatch.setattr(hook.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        hook.sys,
        "argv",
        ["ccb-completion-hook", "--provider", "opencode", "--reply", "done", "--req-id", "r1"],
    )

    rc = hook.main()
    assert rc == 0
    assert captured["pane_id"] == "%2"
    assert captured["terminal"] == "tmux"
    assert "CCB_TASK_COMPLETED" in captured["message"]
