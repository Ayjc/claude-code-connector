from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import laskd_session


def _write_multi_instance_session(work_dir: Path) -> Path:
    cfg = work_dir / ".ccb"
    cfg.mkdir(parents=True, exist_ok=True)
    session_path = cfg / ".claude-session"
    payload = {
        "provider": "claude",
        "default_instance": "1",
        "instances": {
            "1": {
                "instance": "1",
                "terminal": "tmux",
                "pane_id": "%1",
                "pane_title_marker": "CCB-Claude#1",
                "work_dir": str(work_dir),
                "active": True,
            },
            "2": {
                "instance": "2",
                "terminal": "tmux",
                "pane_id": "%2",
                "pane_title_marker": "CCB-Claude#2",
                "work_dir": str(work_dir),
                "active": True,
            },
        },
        "pane_id": "%1",
        "pane_title_marker": "CCB-Claude#1",
        "work_dir": str(work_dir),
    }
    session_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return session_path


def test_load_project_session_selects_explicit_instance(tmp_path: Path) -> None:
    _write_multi_instance_session(tmp_path)
    sess = laskd_session.load_project_session(tmp_path, instance="2")
    assert sess is not None
    assert sess.pane_id == "%2"
    assert sess.data.get("instance") == "2"


def test_load_project_session_ambiguous_without_instance(tmp_path: Path) -> None:
    _write_multi_instance_session(tmp_path)
    with pytest.raises(ValueError, match="Multiple Claude instances"):
        laskd_session.load_project_session(tmp_path)


def test_compute_session_key_includes_instance(tmp_path: Path) -> None:
    _write_multi_instance_session(tmp_path)
    sess = laskd_session.load_project_session(tmp_path, instance="2")
    assert sess is not None
    key = laskd_session.compute_session_key(sess)
    assert ":2" in key


def test_load_project_session_single_instance_no_ambiguity(tmp_path: Path) -> None:
    """When there is only one instance, no ambiguity even without explicit instance."""
    cfg = tmp_path / ".ccb"
    cfg.mkdir(parents=True, exist_ok=True)
    session_path = cfg / ".claude-session"
    payload = {
        "provider": "claude",
        "instances": {
            "1": {
                "instance": "1",
                "terminal": "tmux",
                "pane_id": "%1",
                "work_dir": str(tmp_path),
                "active": True,
            },
        },
        "pane_id": "%1",
        "work_dir": str(tmp_path),
    }
    session_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    sess = laskd_session.load_project_session(tmp_path)
    assert sess is not None
    assert sess.pane_id == "%1"
    assert sess.selected_instance == "1"


def test_load_project_session_instance_not_found(tmp_path: Path) -> None:
    """Requesting a non-existent instance should raise ValueError."""
    _write_multi_instance_session(tmp_path)
    with pytest.raises(ValueError, match="not found"):
        laskd_session.load_project_session(tmp_path, instance="9")


def test_instance_helpers() -> None:
    """Test the helper functions directly."""
    # _normalize_instance_id
    assert laskd_session._normalize_instance_id("2") == "2"
    assert laskd_session._normalize_instance_id("0") is None
    assert laskd_session._normalize_instance_id("abc") is None
    assert laskd_session._normalize_instance_id("100") is None
    assert laskd_session._normalize_instance_id("") is None

    # _instance_entries
    data = {"instances": {"1": {"pane_id": "%1"}, "2": {"pane_id": "%2"}, "bad": "not-dict"}}
    entries = laskd_session._instance_entries(data)
    assert "1" in entries
    assert "2" in entries
    assert "bad" not in entries

    # Empty instances
    assert laskd_session._instance_entries({}) == {}
    assert laskd_session._instance_entries({"instances": "not-dict"}) == {}


def test_compute_session_key_instance_1_no_suffix(tmp_path: Path) -> None:
    """Instance 1 should not add :1 suffix (backward compat)."""
    cfg = tmp_path / ".ccb"
    cfg.mkdir(parents=True, exist_ok=True)
    session_path = cfg / ".claude-session"
    payload = {
        "provider": "claude",
        "pane_id": "%1",
        "work_dir": str(tmp_path),
    }
    session_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    sess = laskd_session.load_project_session(tmp_path)
    assert sess is not None
    key = laskd_session.compute_session_key(sess)
    assert key.startswith("claude:")
    assert ":1" not in key


def test_write_back_preserves_other_instances(tmp_path: Path) -> None:
    """_write_back for instance 2 must not destroy instance 1 data."""
    session_path = _write_multi_instance_session(tmp_path)
    sess = laskd_session.load_project_session(tmp_path, instance="2")
    assert sess is not None

    # Simulate update_claude_binding on instance 2
    sess.data["claude_session_id"] = "new-session-id-for-2"
    sess.data["claude_session_path"] = str(tmp_path / "session2.jsonl")
    sess.data["updated_at"] = "2026-01-01 00:00:00"
    sess._write_back()

    # Re-read the file and verify instance 1 is intact
    data = json.loads(session_path.read_text(encoding="utf-8"))
    assert "instances" in data
    assert data["instances"]["1"]["pane_id"] == "%1"
    assert data["instances"]["1"]["active"] is True
    # Instance 2 should have the updated data
    assert data["instances"]["2"]["claude_session_id"] == "new-session-id-for-2"
    assert data["instances"]["2"]["claude_session_path"] == str(tmp_path / "session2.jsonl")


def test_write_back_instance_1_syncs_to_root(tmp_path: Path) -> None:
    """_write_back for instance 1 should sync key fields to root level."""
    session_path = _write_multi_instance_session(tmp_path)
    sess = laskd_session.load_project_session(tmp_path, instance="1")
    assert sess is not None

    sess.data["claude_session_id"] = "new-root-session-id"
    sess.data["updated_at"] = "2026-01-01 00:00:00"
    sess._write_back()

    data = json.loads(session_path.read_text(encoding="utf-8"))
    # Root level should be synced for instance 1
    assert data.get("claude_session_id") == "new-root-session-id"
    assert data.get("updated_at") == "2026-01-01 00:00:00"
    # Instance 2 should be untouched
    assert data["instances"]["2"]["pane_id"] == "%2"


def test_instance_property() -> None:
    """The instance property should return selected_instance."""
    sess = laskd_session.ClaudeProjectSession(
        session_file=Path("/tmp/fake"),
        data={},
        selected_instance="3",
    )
    assert sess.instance == "3"
