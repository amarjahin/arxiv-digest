"""Tests for schedule.py. The plist renderer is pure, so these run on any OS."""

from __future__ import annotations

import plistlib
from pathlib import Path

from arxiv_digest.schedule import (
    LAUNCHD_LABEL,
    label_for_config,
    log_name_for_config,
    render_launchd_plist,
)


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
    assert spec["StartCalendarInterval"] == [
        {"Weekday": day, "Hour": 19, "Minute": 45} for day in (1, 2, 3, 4, 5)
    ]


def test_plist_skips_weekends():
    days = {entry["Weekday"] for entry in _render()["StartCalendarInterval"]}
    # launchd: 0 and 7 are Sunday, 6 is Saturday.
    assert days.isdisjoint({0, 6, 7})


def test_plist_carries_command_and_paths():
    spec = _render()
    assert spec["ProgramArguments"][0] == "/usr/local/bin/arxiv-digest"
    assert spec["ProgramArguments"][-1] == "/home/me/config.yaml"
    assert spec["WorkingDirectory"] == "/home/me"
    assert spec["StandardOutPath"] == "/home/me/arxiv-digest.log"
    # Don't fire on load — only at the scheduled time.
    assert spec["RunAtLoad"] is False


def test_default_config_keeps_original_label():
    # Existing installs of config.yaml must keep resolving to the same job.
    assert label_for_config(Path("/home/me/config.yaml")) == LAUNCHD_LABEL
    assert log_name_for_config(Path("/home/me/config.yaml")) == "arxiv-digest.log"


def test_other_configs_get_their_own_label_and_log():
    assert label_for_config(Path("/home/me/config1.yaml")) == f"{LAUNCHD_LABEL}.config1"
    assert log_name_for_config(Path("/home/me/config1.yaml")) == "arxiv-digest-config1.log"


def test_label_sanitizes_odd_characters():
    assert label_for_config(Path("my config.yaml")) == f"{LAUNCHD_LABEL}.my-config"
