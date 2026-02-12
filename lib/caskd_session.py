from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from ccb_config import apply_backend_env
from project_id import compute_ccb_project_id
from session_utils import find_project_session_file as _find_project_session_file, safe_write_session
from terminal import get_backend_for_session

apply_backend_env()


def find_project_session_file(work_dir: Path) -> Optional[Path]:
    return _find_project_session_file(work_dir, ".codex-session")


def _read_json(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8-sig")
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _normalize_instance_id(raw: object) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    if not value.isdigit():
        return ""
    num = int(value)
    if num < 1 or num > 99:
        return ""
    return str(num)


def _instance_entries(data: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    raw = data.get("instances")
    if not isinstance(raw, dict):
        return out
    for key, entry in raw.items():
        iid = _normalize_instance_id(key)
        if not iid or not isinstance(entry, dict):
            continue
        out[iid] = dict(entry)
    return out


def _entry_active(entry: dict) -> bool:
    if not isinstance(entry, dict):
        return False
    return entry.get("active") is not False


def _select_instance_data(data: dict, explicit_instance: Optional[str]) -> tuple[str, dict, dict[str, dict]]:
    instances = _instance_entries(data)
    if not instances:
        if explicit_instance and explicit_instance != "1":
            raise ValueError(f"Codex instance {explicit_instance} not found.")
        return "1", dict(data), {}

    if explicit_instance:
        selected = instances.get(explicit_instance)
        if not selected:
            raise ValueError(f"Codex instance {explicit_instance} not found.")
        return explicit_instance, selected, instances

    if len(instances) == 1:
        iid, selected = next(iter(instances.items()))
        return iid, selected, instances

    active_instances = [iid for iid, entry in instances.items() if _entry_active(entry)]
    if len(active_instances) == 1:
        iid = active_instances[0]
        selected = instances.get(iid) or {}
        return iid, selected, instances

    raise ValueError("Multiple Codex instances are active; please specify --instance N.")


@dataclass
class CodexProjectSession:
    session_file: Path
    data: dict
    selected_instance: str = "1"
    root_data: Optional[dict] = None

    @property
    def terminal(self) -> str:
        return (self.data.get("terminal") or "tmux").strip() or "tmux"

    @property
    def pane_id(self) -> str:
        v = self.data.get("pane_id")
        if not v and self.terminal == "tmux":
            v = self.data.get("tmux_session")
        return str(v or "").strip()

    @property
    def pane_title_marker(self) -> str:
        return str(self.data.get("pane_title_marker") or "").strip()

    @property
    def codex_session_path(self) -> str:
        return str(self.data.get("codex_session_path") or "").strip()

    @property
    def codex_session_id(self) -> str:
        return str(self.data.get("codex_session_id") or "").strip()

    @property
    def work_dir(self) -> str:
        return str(self.data.get("work_dir") or self.session_file.parent)

    @property
    def runtime_dir(self) -> Path:
        return Path(self.data.get("runtime_dir") or self.session_file.parent)

    @property
    def instance(self) -> str:
        iid = _normalize_instance_id(self.selected_instance)
        return iid or "1"

    @property
    def start_cmd(self) -> str:
        # Prefer explicit codex_start_cmd when present.
        return str(self.data.get("codex_start_cmd") or self.data.get("start_cmd") or "").strip()

    def backend(self):
        return get_backend_for_session(self.data)

    def _attach_pane_log(self, backend: object, pane_id: str) -> None:
        ensure = getattr(backend, "ensure_pane_log", None)
        if callable(ensure):
            try:
                ensure(str(pane_id))
            except Exception:
                pass

    def ensure_pane(self) -> Tuple[bool, str]:
        backend = self.backend()
        if not backend:
            return False, "Terminal backend not available"

        pane_id = self.pane_id
        if pane_id and backend.is_alive(pane_id):
            self._attach_pane_log(backend, pane_id)
            return True, pane_id

        marker = self.pane_title_marker
        resolver = getattr(backend, "find_pane_by_title_marker", None)
        resolved: Optional[str] = None
        if marker and callable(resolver):
            resolved = resolver(marker)
            if resolved and backend.is_alive(str(resolved)):
                self.data["pane_id"] = str(resolved)
                self.data["updated_at"] = _now_str()
                self._write_back()
                self._attach_pane_log(backend, str(resolved))
                return True, str(resolved)

        # tmux self-heal: if pane exists but is dead (remain-on-exit), respawn in-place.
        if self.terminal == "tmux":
            start_cmd = self.start_cmd
            respawn = getattr(backend, "respawn_pane", None)
            if start_cmd and callable(respawn):
                last_err: str | None = None
                for target in [resolved, pane_id]:
                    if not target or not str(target).startswith("%"):
                        continue
                    try:
                        saver = getattr(backend, "save_crash_log", None)
                        if callable(saver):
                            try:
                                runtime = self.runtime_dir
                                runtime.mkdir(parents=True, exist_ok=True)
                                crash_log = runtime / f"pane-crash-{int(time.time())}.log"
                                saver(str(target), str(crash_log), lines=1000)
                            except Exception:
                                pass
                        respawn(str(target), cmd=start_cmd, cwd=self.work_dir, remain_on_exit=True)
                        if backend.is_alive(str(target)):
                            self.data["pane_id"] = str(target)
                            self.data["updated_at"] = _now_str()
                            self._write_back()
                            self._attach_pane_log(backend, str(target))
                            return True, str(target)
                        last_err = "respawn did not revive pane"
                    except Exception as exc:
                        last_err = f"{exc}"
                if last_err:
                    return False, f"Pane not alive and respawn failed: {last_err}"

        return False, f"Pane not alive: {pane_id}"

    def update_codex_log_binding(self, *, log_path: Optional[str], session_id: Optional[str]) -> None:
        old_path = str(self.data.get("codex_session_path") or "").strip()
        old_id = str(self.data.get("codex_session_id") or "").strip()

        updated = False
        log_path_str = ""
        if log_path:
            log_path_str = str(log_path).strip()
        if log_path_str and self.data.get("codex_session_path") != log_path_str:
            self.data["codex_session_path"] = log_path_str
            updated = True
        if session_id and self.data.get("codex_session_id") != session_id:
            self.data["codex_session_id"] = session_id
            self.data["codex_start_cmd"] = f"codex resume {session_id}"
            updated = True

        if updated:
            new_id = str(session_id or "").strip()
            if not new_id and log_path_str:
                try:
                    new_id = Path(log_path_str).stem
                except Exception:
                    new_id = ""
            if old_id and old_id != new_id:
                self.data["old_codex_session_id"] = old_id
            if old_path and (old_path != log_path_str or (old_id and old_id != new_id)):
                self.data["old_codex_session_path"] = old_path
            if old_path or old_id:
                self.data["old_updated_at"] = _now_str()
                try:
                    from ctx_transfer_utils import maybe_auto_transfer

                    old_path_obj = None
                    if old_path:
                        try:
                            old_path_obj = Path(old_path).expanduser()
                        except Exception:
                            old_path_obj = None
                    maybe_auto_transfer(
                        provider="codex",
                        work_dir=Path(self.work_dir),
                        session_path=old_path_obj,
                        session_id=old_id or None,
                    )
                except Exception:
                    pass

            self.data["updated_at"] = _now_str()
            if self.data.get("active") is False:
                self.data["active"] = True
            self._write_back()

    def _write_back(self) -> None:
        payload_data = self.data
        if isinstance(self.root_data, dict):
            root = self.root_data
            instances = root.get("instances")
            if isinstance(instances, dict):
                iid = self.instance
                entry = instances.get(iid)
                if not isinstance(entry, dict):
                    entry = {}
                    instances[iid] = entry
                for key, value in self.data.items():
                    if key.startswith("_") or key in {"instances", "default_instance", "instance"}:
                        continue
                    entry[key] = value
                root["provider"] = "codex"
                root["default_instance"] = str(root.get("default_instance") or "1")
                if iid == "1":
                    for key in (
                        "pane_id",
                        "pane_title_marker",
                        "runtime_dir",
                        "input_fifo",
                        "output_fifo",
                        "tmux_log",
                        "tmux_session",
                        "terminal",
                        "work_dir",
                        "work_dir_norm",
                        "start_dir",
                        "active",
                        "started_at",
                        "codex_start_cmd",
                        "start_cmd",
                        "codex_session_path",
                        "codex_session_id",
                        "updated_at",
                    ):
                        if key in entry:
                            root[key] = entry.get(key)
                payload_data = root

        payload = json.dumps(payload_data, ensure_ascii=False, indent=2) + "\n"
        ok, err = safe_write_session(self.session_file, payload)
        if not ok:
            # Best-effort: never raise (daemon should continue).
            _ = err


def load_project_session(work_dir: Path, instance: Optional[str] = None) -> Optional[CodexProjectSession]:
    session_file = find_project_session_file(work_dir)
    if not session_file:
        return None
    root = _read_json(session_file)
    if not root:
        return None
    explicit = None
    if instance is not None:
        explicit = _normalize_instance_id(instance)
        if not explicit:
            raise ValueError("--instance must be an integer between 1 and 99")

    selected_iid, selected_data, instances = _select_instance_data(root, explicit)
    data = dict(root)
    data.update(selected_data)
    data["instance"] = selected_iid

    root_data = root if instances else None
    return CodexProjectSession(
        session_file=session_file,
        data=data,
        selected_instance=selected_iid,
        root_data=root_data,
    )


def compute_session_key(session: CodexProjectSession) -> str:
    """
    Compute the daemon routing/serialization key for this provider.

    Hard rule: include provider + ccb_project_id to isolate projects and providers.
    """
    pid = str(session.data.get("ccb_project_id") or "").strip()
    if not pid:
        try:
            pid = compute_ccb_project_id(Path(session.work_dir))
        except Exception:
            pid = ""
    iid = session.instance
    return f"codex:{pid}:{iid}" if pid else f"codex:unknown:{iid}"
