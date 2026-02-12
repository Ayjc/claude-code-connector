from __future__ import annotations

from pathlib import Path


def _make_session(tmp_path: Path, filename: str) -> Path:
    root = tmp_path / "proj"
    cfg = root / ".ccb"
    cfg.mkdir(parents=True)
    session = cfg / filename
    session.write_text("{}", encoding="utf-8")
    return session


def test_codex_comm_find_session_file_prefers_ccb_session_file(tmp_path: Path, monkeypatch) -> None:
    from codex_comm import CodexCommunicator

    session = _make_session(tmp_path, ".codex-session")
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    monkeypatch.setenv("CCB_SESSION_FILE", str(session))

    comm = object.__new__(CodexCommunicator)
    assert comm._find_session_file() == session


def test_codex_comm_find_session_file_ignores_wrong_filename(tmp_path: Path, monkeypatch) -> None:
    from codex_comm import CodexCommunicator

    session = _make_session(tmp_path, ".gemini-session")
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    monkeypatch.setenv("CCB_SESSION_FILE", str(session))

    comm = object.__new__(CodexCommunicator)
    assert comm._find_session_file() is None


def test_gemini_comm_find_session_file_prefers_ccb_session_file(tmp_path: Path, monkeypatch) -> None:
    from gemini_comm import GeminiCommunicator

    session = _make_session(tmp_path, ".gemini-session")
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    monkeypatch.setenv("CCB_SESSION_FILE", str(session))

    comm = object.__new__(GeminiCommunicator)
    assert comm._find_session_file() == session


def test_opencode_comm_find_session_file_prefers_ccb_session_file(tmp_path: Path, monkeypatch) -> None:
    from opencode_comm import OpenCodeCommunicator

    session = _make_session(tmp_path, ".opencode-session")
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    monkeypatch.setenv("CCB_SESSION_FILE", str(session))

    comm = object.__new__(OpenCodeCommunicator)
    assert comm._find_session_file() == session


def test_codex_comm_select_instance_for_log_binding_prefers_session_id() -> None:
    from codex_comm import _select_instance_for_log_binding

    session_data = {
        "default_instance": "1",
        "instances": {
            "1": {"active": True, "codex_session_id": "sid-1"},
            "2": {"active": True, "codex_session_id": "sid-2"},
        },
    }
    got = _select_instance_for_log_binding(session_data, session_id="sid-2", log_path="/tmp/x.jsonl")
    assert got == "2"


def test_codex_comm_select_instance_for_log_binding_uses_single_active() -> None:
    from codex_comm import _select_instance_for_log_binding

    session_data = {
        "instances": {
            "1": {"active": True},
            "2": {"active": False},
        },
    }
    got = _select_instance_for_log_binding(session_data, session_id="", log_path="/tmp/x.jsonl")
    assert got == "1"


def test_codex_comm_select_instance_for_log_binding_ambiguous_without_default() -> None:
    from codex_comm import _select_instance_for_log_binding

    session_data = {
        "instances": {
            "1": {"active": True},
            "2": {"active": True},
        },
    }
    got = _select_instance_for_log_binding(session_data, session_id="", log_path="")
    assert got is None
