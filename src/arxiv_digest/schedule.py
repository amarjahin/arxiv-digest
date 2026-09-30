"""Install/uninstall a recurring daily run with the OS scheduler.

macOS uses a launchd LaunchAgent. Linux (systemd) and Windows (Task Scheduler)
are planned follow-ups; calling into them now raises a clear error.

The plist is rendered by a pure function (`render_launchd_plist`) so it can be
unit-tested on any OS. The side-effecting install/uninstall/status helpers are
thin wrappers around `launchctl`.
"""

from __future__ import annotations

import platform
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

LAUNCHD_LABEL = "com.arxiv-digest.daily"

# launchd weekdays: 0/7 = Sunday, 1 = Monday … 6 = Saturday. arXiv doesn't
# announce on weekends, so only fire Monday–Friday.
WEEKDAYS = (1, 2, 3, 4, 5)


class ScheduleError(Exception):
    """Raised with a user-facing message when scheduling can't proceed."""


# ---------------------------------------------------------------------------
# Command + path resolution
# ---------------------------------------------------------------------------

def _resolve_command(config_path: Path) -> list[str]:
    """The argv the scheduler should run each day.

    Prefer the installed `arxiv-digest` console script; fall back to
    `python -m arxiv_digest` so this keeps working in editable/venv installs
    where the script may not be on the scheduler's PATH.
    """
    binary = shutil.which("arxiv-digest")
    cfg = str(config_path.resolve())
    if binary:
        return [binary, "run", "--config", cfg]
    return [sys.executable, "-m", "arxiv_digest", "run", "--config", cfg]


# ---------------------------------------------------------------------------
# macOS / launchd
# ---------------------------------------------------------------------------

def render_launchd_plist(
    *,
    command: list[str],
    hour: int,
    minute: int,
    working_dir: Path,
    log_path: Path,
    label: str = LAUNCHD_LABEL,
) -> bytes:
    """Render a launchd plist as bytes. Pure — no filesystem side effects."""
    spec: dict[str, object] = {
        "Label": label,
        "ProgramArguments": command,
        "StartCalendarInterval": [
            {"Weekday": day, "Hour": hour, "Minute": minute} for day in WEEKDAYS
        ],
        "WorkingDirectory": str(working_dir),
        "StandardOutPath": str(log_path),
        "StandardErrorPath": str(log_path),
        "RunAtLoad": False,
    }
    return plistlib.dumps(spec)


def label_for_config(config_path: Path) -> str:
    """launchd label for a config, so each config gets its own job.

    `config.yaml` keeps the original bare label (existing installs stay
    valid); any other config gets a suffix from its file stem, e.g.
    `config1.yaml` -> `com.arxiv-digest.daily.config1`.
    """
    stem = config_path.stem
    if stem == "config":
        return LAUNCHD_LABEL
    safe = re.sub(r"[^A-Za-z0-9_-]", "-", stem)
    return f"{LAUNCHD_LABEL}.{safe}"


def log_name_for_config(config_path: Path) -> str:
    """Per-config log filename, so concurrent jobs don't interleave output."""
    stem = config_path.stem
    if stem == "config":
        return "arxiv-digest.log"
    return f"arxiv-digest-{re.sub(r'[^A-Za-z0-9_-]', '-', stem)}.log"


def _launchd_plist_path(label: str = LAUNCHD_LABEL) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def _install_macos(*, config_path: Path, hour: int, minute: int) -> Path:
    config_path = config_path.resolve()
    working_dir = config_path.parent
    log_path = working_dir / log_name_for_config(config_path)
    label = label_for_config(config_path)
    plist_path = _launchd_plist_path(label)
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    data = render_launchd_plist(
        command=_resolve_command(config_path),
        hour=hour,
        minute=minute,
        working_dir=working_dir,
        log_path=log_path,
        label=label,
    )
    plist_path.write_bytes(data)

    # Reload: unload first (ignore errors), then load the fresh plist.
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True, check=False)
    res = subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, check=False)
    if res.returncode != 0:
        raise ScheduleError(
            f"launchctl load failed: {res.stderr.decode(errors='replace').strip()}"
        )
    return plist_path


def _uninstall_macos(config_path: Path) -> bool:
    plist_path = _launchd_plist_path(label_for_config(config_path))
    if not plist_path.exists():
        return False
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True, check=False)
    plist_path.unlink()
    return True


def _status_macos() -> str:
    agents_dir = _launchd_plist_path().parent
    plists = sorted(agents_dir.glob(f"{LAUNCHD_LABEL}*.plist"))
    if not plists:
        return "Not installed."
    lines = []
    for plist_path in plists:
        spec = plistlib.loads(plist_path.read_bytes())
        label = spec.get("Label", plist_path.stem)
        args = spec.get("ProgramArguments", [])
        config = args[-1] if args else "?"
        res = subprocess.run(["launchctl", "list", label], capture_output=True, check=False)
        loaded = "loaded" if res.returncode == 0 else "present but not loaded"
        lines.append(f"{config}: installed at {plist_path} ({loaded}).")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public dispatch
# ---------------------------------------------------------------------------

def _unsupported(action: str) -> ScheduleError:
    system = platform.system() or "this platform"
    return ScheduleError(
        f"Scheduling is not yet supported on {system}; only macOS is implemented. "
        f"Cannot {action}."
    )


def install(*, config_path: Path, hour: int, minute: int) -> Path:
    """Install (or replace) the daily scheduled run. Returns the job file path."""
    if platform.system() == "Darwin":
        return _install_macos(config_path=config_path, hour=hour, minute=minute)
    raise _unsupported("install")


def uninstall(*, config_path: Path) -> bool:
    """Remove the scheduled run for this config. Returns True if something was removed."""
    if platform.system() == "Darwin":
        return _uninstall_macos(config_path)
    raise _unsupported("uninstall")


def status() -> str:
    """Human-readable description of every installed scheduled run."""
    if platform.system() == "Darwin":
        return _status_macos()
    raise _unsupported("report status")
