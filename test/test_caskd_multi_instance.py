from __future__ import annotations

import json
from pathlib import Path

import pytest

import caskd_session


def _write_multi_instance_session(work_dir: Path) -> Path:
    cfg = work_dir / ".ccb"
    cfg.mkdir(parents=True, exist_ok=True)
    session_path = cfg / ".codex-session"
    payload = {
        "provider": "codex",
        "default_instance": "1",
        "instances": {
            "1": {
                "instance": "1",
                "terminal": "tmux",
                "pane_id": "%1",
                "pane_title_marker": "CCB-Codex#1",
                "work_dir": str(work_dir),
                "active": True,
            },
            "2": {
                "instance": "2",
                "terminal": "tmux",
                "pane_id": "%2",
                "pane_title_marker": "CCB-Codex#2",
                "work_dir": str(work_dir),
                "active": True,
            },
        },
        "pane_id": "%1",
        "pane_title_marker": "CCB-Codex#1",
        "work_dir": str(work_dir),
    }
    session_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return session_path


def test_load_project_session_requires_instance_when_multiple(tmp_path: Path) -> None:
    _write_multi_instance_session(tmp_path)
    with pytest.raises(ValueError, match="Multiple Codex instances"):
        caskd_session.load_project_session(tmp_path)


def test_load_project_session_selects_explicit_instance(tmp_path: Path) -> None:
    _write_multi_instance_session(tmp_path)
    sess = caskd_session.load_project_session(tmp_path, instance="2")
    assert sess is not None
    assert sess.instance == "2"
    assert sess.pane_id == "%2"
    assert caskd_session.compute_session_key(sess).endswith(":2")


def test_update_codex_log_binding_updates_selected_instance_only(tmp_path: Path) -> None:
    session_path = _write_multi_instance_session(tmp_path)
    sess = caskd_session.load_project_session(tmp_path, instance="2")
    assert sess is not None

    sess.update_codex_log_binding(
        log_path=str(tmp_path / "session2.jsonl"),
        session_id="22222222-2222-2222-2222-222222222222",
    )

    data = json.loads(session_path.read_text(encoding="utf-8"))
    assert data["instances"]["2"]["codex_session_id"] == "22222222-2222-2222-2222-222222222222"
    assert data.get("codex_session_id") != "22222222-2222-2222-2222-222222222222"
