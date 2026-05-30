"""Tests for schedule.py. The plist renderer is pure, so these run on any OS."""

from __future__ import annotations

import plistlib
from pathlib import Path

from arxiv_digest.schedule import LAUNCHD_LABEL, render_launchd_plist


def _render() -> dict:
    data = render_launchd_plist(
        command=["/usr/local/bin/arxiv-digest", "run", "--config", "/home/me/config.yaml"],
        hour=19,
        minute=45,
        working_dir=Path("/home/me"),
        log_path=Path("/home/me/arxiv-digest.log"),
    )
    return plistlib.loads(data)


def test_plist_is_valid_and_labeled():
    spec = _render()
    assert spec["Label"] == LAUNCHD_LABEL


def test_plist_encodes_run_time():
    spec = _render()
    assert spec["StartCalendarInterval"] == {"Hour": 19, "Minute": 45}


def test_plist_carries_command_and_paths():
    spec = _render()
    assert spec["ProgramArguments"][0] == "/usr/local/bin/arxiv-digest"
    assert spec["ProgramArguments"][-1] == "/home/me/config.yaml"
    assert spec["WorkingDirectory"] == "/home/me"
    assert spec["StandardOutPath"] == "/home/me/arxiv-digest.log"
    # Don't fire on load — only at the scheduled time.
    assert spec["RunAtLoad"] is False
