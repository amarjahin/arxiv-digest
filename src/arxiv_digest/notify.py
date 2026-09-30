"""Desktop notifications for the end of a digest run.

OS-detecting: each platform has its own backend. macOS is implemented; Linux
and Windows are stubs for now (filled in by follow-up work). A notification
failure must never break a run, so every backend swallows its own errors.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path


def send(
    *,
    title: str,
    message: str,
    open_path: Path | None = None,
    enabled: bool = True,
) -> None:
    """Show a desktop banner. No-op when disabled or unsupported.

    `open_path`, if given, is the folder a clickable banner should open
    (supported on macOS; ignored where the platform can't do it reliably).
    """
    if not enabled:
        return
    system = platform.system()
    try:
        if system == "Darwin":
            _send_macos(title, message, open_path)
        # Linux ("Linux") and Windows ("Windows") backends land in later work.
    except Exception:
        # A failed notification is never worth failing the run over.
        pass


def _send_macos(title: str, message: str, open_path: Path | None) -> None:
    """macOS banner. Prefers terminal-notifier (clickable) and falls back to
    osascript (not clickable, but always available)."""
    tn = shutil.which("terminal-notifier")
    if tn:
        args = [tn, "-title", title, "-message", message, "-sound", "Glass"]
        if open_path is not None:
            args += ["-execute", f"open {_shquote(str(open_path))}"]
        subprocess.run(args, check=False, capture_output=True)
        return

    # Fallback: osascript banners can't carry a click action.
    script = f'display notification {_osa(message)} with title {_osa(title)} sound name "Glass"'
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def _osa(s: str) -> str:
    """Quote a string as an AppleScript string literal."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _shquote(s: str) -> str:
    """Single-quote a string for a POSIX shell."""
    return "'" + s.replace("'", "'\\''") + "'"
