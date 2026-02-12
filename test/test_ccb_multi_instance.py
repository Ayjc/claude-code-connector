from __future__ import annotations

import importlib.util
import json
from importlib.machinery import SourceFileLoader
from pathlib import Path


def _load_ccb_module() -> object:
    repo_root = Path(__file__).resolve().parents[1]
    ccb_path = repo_root / "ccb"
    loader = SourceFileLoader("ccb_script_multi", str(ccb_path))
    spec = importlib.util.spec_from_loader("ccb_script_multi", loader)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_parse_providers_with_cmd_counts_duplicates() -> None:
    ccb = _load_ccb_module()
    providers, cmd_enabled, counts = ccb._parse_providers_with_cmd(["codex", "codex", "claude"])
    assert providers == ["codex", "claude"]
    assert cmd_enabled is False
    assert counts.get("codex") == 2


def test_parse_instance_overrides_codex_only() -> None:
    ccb = _load_ccb_module()
    overrides, errors = ccb._parse_instance_overrides(["codex=3"])
    assert errors == []
    assert overrides == {"codex": 3}

    bad_overrides, bad_errors = ccb._parse_instance_overrides(["gemini=2"])
    assert bad_overrides == {}
    assert bad_errors


def test_run_up_starts_codex_multi_instances(monkeypatch, tmp_path: Path) -> None:
    ccb = _load_ccb_module()
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".ccb").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TMUX_PANE", "%0")
    monkeypatch.setattr(ccb, "detect_terminal", lambda: "tmux")

    launcher = ccb.AILauncher(
        providers=["codex", "claude"],
        instance_counts={"codex": 2},
    )
    launcher.terminal_type = "tmux"

    called: list[str] = []

    def _start_provider(provider: str, **_kwargs) -> str:
        called.append(provider)
        return f"%{len(called)}"

    monkeypatch.setattr(launcher, "_start_provider", _start_provider)
    monkeypatch.setattr(launcher, "_warmup_provider", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(launcher, "_maybe_start_caskd", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(launcher, "_start_provider_in_current_pane", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(launcher, "cleanup", lambda **_kwargs: None)

    rc = launcher.run_up()
    assert rc == 0
    assert called == ["codex#2", "codex#1"]


def test_single_instance_write_deactivates_legacy_extra_instances(monkeypatch, tmp_path: Path) -> None:
    ccb = _load_ccb_module()
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / ".ccb"
    cfg.mkdir(parents=True, exist_ok=True)
    session_file = cfg / ".codex-session"
    session_file.write_text(
        json.dumps(
            {
                "provider": "codex",
                "default_instance": "1",
                "instances": {
                    "1": {"instance": "1", "active": True, "pane_id": "%1"},
                    "2": {"instance": "2", "active": True, "pane_id": "%2"},
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    launcher = ccb.AILauncher(
        providers=["codex", "claude"],
        instance_counts={"codex": 1},
    )
    monkeypatch.setattr(launcher, "_maybe_start_provider_daemon", lambda *_args, **_kwargs: None)

    ok = launcher._write_codex_session(
        runtime=tmp_path / "runtime-codex",
        tmux_session=None,
        input_fifo=tmp_path / "input.fifo",
        output_fifo=tmp_path / "output.fifo",
        pane_id="%9",
        pane_title_marker="CCB-Codex#1",
        codex_start_cmd="codex",
        codex_instance="1",
    )
    assert ok is True

    data = json.loads(session_file.read_text(encoding="utf-8"))
    assert data["instances"]["1"]["active"] is True
    assert data["instances"]["2"]["active"] is False
