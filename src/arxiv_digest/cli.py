"""Command-line entry point.

Usage:
    arxiv-digest run [--config PATH] [--dry-run]
    arxiv-digest validate-config [--config PATH]
    arxiv-digest init [--config PATH] [--force]
"""

from __future__ import annotations

import random
import shutil
import sys
from datetime import date
from pathlib import Path

import click
from rich.console import Console

from . import __version__, notify, schedule
from .config import ConfigError, load_config
from .fetch import ArxivClient, fetch_category
from .filter import filter_papers
from .mailer import EmailError, send_digest
from .render import prune_digests, render_markdown, write_digest
from .schedule import ScheduleError

console = Console()
err_console = Console(stderr=True, style="red")

DEFAULT_CONFIG_PATH = Path("config.yaml")
EXAMPLE_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.example.yaml"


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="arxiv-digest")
def main() -> None:
    """Daily arXiv digest filtered by author and keyword."""


@main.command()
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_CONFIG_PATH,
    show_default=True,
    help="Path to YAML config.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Fetch and filter but don't write the digest file.",
)
@click.option(
    "--email/--no-email",
    "email_override",
    default=None,
    help="Force email on/off, overriding config.email.enabled.",
)
@click.option(
    "--notify/--no-notify",
    "notify_override",
    default=None,
    help="Force the desktop notification on/off, overriding config.notify.enabled.",
)
def run(
    config_path: Path,
    dry_run: bool,
    email_override: bool | None,
    notify_override: bool | None,
) -> None:
    """Fetch today's arXiv submissions, filter, and write a digest."""
    try:
        cfg = load_config(config_path)
    except ConfigError as e:
        err_console.print(str(e))
        sys.exit(2)

    filters = cfg.to_filter_config()

    all_papers = []
    seen_ids: set[str] = set()
    with ArxivClient(
        user_agent=cfg.http.user_agent,
        min_interval_seconds=cfg.http.min_interval_seconds,
        timeout_seconds=cfg.http.timeout_seconds,
    ) as client:
        for category in cfg.categories:
            console.print(f"[dim]Fetching[/dim] {category} …")
            try:
                papers = fetch_category(client, category)
            except Exception as e:  # network or HTTP error
                err_console.print(f"  failed: {e}")
                continue
            new_count = 0
            for p in papers:
                if p.arxiv_id in seen_ids:
                    continue
                seen_ids.add(p.arxiv_id)
                all_papers.append(p)
                new_count += 1
            console.print(f"  got {new_count} unique papers")

    total = len(all_papers)
    matched = filter_papers(all_papers, filters)
    console.print(f"\n[bold]{len(matched)}[/bold] matches out of {total} new submissions.")

    matched_ids = {p.arxiv_id for p in matched}
    unmatched = [p for p in all_papers if p.arxiv_id not in matched_ids]
    n_random = min(cfg.output.random_count, len(unmatched))
    random_picks = random.sample(unmatched, n_random) if n_random else []

    if dry_run:
        for p in matched[:20]:
            console.print(f"  {p.arxiv_id}  {p.title[:80]}")
        if len(matched) > 20:
            console.print(f"  … and {len(matched) - 20} more")
        if random_picks:
            console.print(f"\n[dim]random picks ({len(random_picks)}):[/dim]")
            for p in random_picks:
                console.print(f"  {p.arxiv_id}  {p.title[:80]}")
        return

    today = date.today()
    md = render_markdown(
        matched,
        categories=cfg.categories,
        total_seen=total,
        run_date=today,
        include_abstract=cfg.output.include_abstract,
        group_by=cfg.output.group_by,
        keyword_priority=filters.keywords_any_of,
        random_papers=random_picks,
    )
    path = write_digest(md, cfg.output.dir, today, primary_category=cfg.categories[0])
    console.print(f"Wrote [green]{path}[/green]")

    if cfg.output.keep_days is not None:
        removed = prune_digests(cfg.output.dir, today, cfg.output.keep_days)
        if removed:
            console.print(
                f"Removed [dim]{len(removed)}[/dim] digest{'s' if len(removed) != 1 else ''} "
                f"older than {cfg.output.keep_days} days"
            )

    should_email = cfg.email.enabled if email_override is None else email_override
    if should_email:
        try:
            send_digest(cfg.email, body=md, run_date=today, attachment_path=path)
        except EmailError as e:
            err_console.print(f"Email send failed: {e}")
            sys.exit(3)
        n = len(cfg.email.to)
        console.print(f"Emailed digest to [green]{n}[/green] recipient{'s' if n != 1 else ''}")

    should_notify = cfg.notify.enabled if notify_override is None else notify_override
    if should_notify:
        open_path = cfg.output.dir.resolve() if cfg.notify.open_on_click else None
        notify.send(
            title="arXiv digest",
            message=f"{len(matched)} matches out of {total} new submissions",
            open_path=open_path,
            enabled=True,
        )


@main.command("validate-config")
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_CONFIG_PATH,
    show_default=True,
)
def validate_config(config_path: Path) -> None:
    """Load and validate the config; print the resolved values."""
    try:
        cfg = load_config(config_path)
    except ConfigError as e:
        err_console.print(str(e))
        sys.exit(2)
    console.print(f"[green]OK[/green] {config_path}")
    console.print_json(cfg.model_dump_json(indent=2))


@main.command()
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_CONFIG_PATH,
    show_default=True,
    help="Where to write the config.",
)
@click.option("--force", is_flag=True, help="Overwrite if the file already exists.")
def init(config_path: Path, force: bool) -> None:
    """Write a starter config to the given path."""
    if config_path.exists() and not force:
        err_console.print(f"{config_path} already exists. Pass --force to overwrite.")
        sys.exit(1)
    if not EXAMPLE_CONFIG_PATH.exists():
        err_console.print(f"Bundled example missing: {EXAMPLE_CONFIG_PATH}")
        sys.exit(1)
    shutil.copy(EXAMPLE_CONFIG_PATH, config_path)
    console.print(f"Wrote [green]{config_path}[/green]. Edit it, then run `arxiv-digest run`.")


# Named "schedule" explicitly; the function can't be (it would shadow the
# imported `schedule` module).
@main.group("schedule")
def schedule_cmd() -> None:
    """Manage the daily scheduled run (macOS launchd)."""


@schedule_cmd.command("install")
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_CONFIG_PATH,
    show_default=True,
    help="Path to YAML config; its schedule.* fields set the run time.",
)
def schedule_install(config_path: Path) -> None:
    """Install (or replace) this config's daily run from config.schedule.

    Each config file gets its own job, so several configs can be scheduled
    side by side."""
    try:
        cfg = load_config(config_path)
    except ConfigError as e:
        err_console.print(str(e))
        sys.exit(2)
    if not cfg.schedule.enabled:
        err_console.print(
            "config.schedule.enabled is false — set it to true (and hour/minute) first."
        )
        sys.exit(1)
    try:
        path = schedule.install(
            config_path=config_path,
            hour=cfg.schedule.hour,
            minute=cfg.schedule.minute,
        )
    except ScheduleError as e:
        err_console.print(str(e))
        sys.exit(4)
    console.print(
        f"Scheduled weekdays at [bold]{cfg.schedule.hour:02d}:{cfg.schedule.minute:02d}[/bold]. "
        f"Job: [green]{path}[/green]"
    )


@schedule_cmd.command("uninstall")
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_CONFIG_PATH,
    show_default=True,
    help="Config whose scheduled run to remove.",
)
def schedule_uninstall(config_path: Path) -> None:
    """Remove the daily scheduled run for one config."""
    try:
        removed = schedule.uninstall(config_path=config_path)
    except ScheduleError as e:
        err_console.print(str(e))
        sys.exit(4)
    if removed:
        console.print(f"Removed the scheduled run for {config_path}.")
    else:
        console.print(f"Nothing to remove — no scheduled run was installed for {config_path}.")


@schedule_cmd.command("status")
def schedule_status() -> None:
    """Show every installed daily run (one per config)."""
    try:
        console.print(schedule.status())
    except ScheduleError as e:
        err_console.print(str(e))
        sys.exit(4)


if __name__ == "__main__":
    main()
