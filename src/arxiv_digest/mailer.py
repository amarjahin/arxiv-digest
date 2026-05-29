"""Send a rendered digest via SMTP.

The SMTP password is read from the env var named by `config.email.password_env`,
never from the config file itself — so the config is safe to commit.
"""

from __future__ import annotations

import os
import smtplib
from datetime import date
from email.message import EmailMessage
from pathlib import Path

from .config import Email


class EmailError(Exception):
    """Raised when SMTP delivery cannot be performed."""


def send_digest(
    cfg: Email,
    *,
    body: str,
    run_date: date,
    attachment_path: Path | None = None,
) -> None:
    """Send `body` (the rendered markdown) to `cfg.to`. Optionally attach the
    .md file. Raises EmailError on misconfiguration or SMTP failure."""
    if not cfg.to:
        raise EmailError("email.to is empty")
    if not cfg.username:
        raise EmailError("email.username is required (your SMTP login address)")

    password = os.environ.get(cfg.password_env)
    if not password:
        raise EmailError(
            f"env var {cfg.password_env} is unset — set it to your SMTP app password"
        )

    msg = EmailMessage()
    msg["From"] = cfg.from_addr or cfg.username
    msg["To"] = ", ".join(cfg.to)
    msg["Subject"] = cfg.subject.format(date=run_date.isoformat())
    msg.set_content(body)

    if cfg.attach_file and attachment_path is not None and attachment_path.exists():
        msg.add_attachment(
            attachment_path.read_bytes(),
            maintype="text",
            subtype="markdown",
            filename=attachment_path.name,
        )

    try:
        with smtplib.SMTP(cfg.host, cfg.port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(cfg.username, password)
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise EmailError(f"SMTP send failed: {e}") from e
