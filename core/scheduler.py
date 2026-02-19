"""
core/scheduler.py — APScheduler in-process background polling

Polls Odds API every 5 minutes and logs line snapshots to SQLite.
Designed for Streamlit: guarded against re-initialization on every rerun.

Usage in app.py:
    from core.scheduler import start_scheduler, stop_scheduler, get_status
    if "scheduler_started" not in st.session_state:
        start_scheduler()
        st.session_state["scheduler_started"] = True
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from core.odds_fetcher import fetch_batch_odds, quota
from core.line_logger import init_db, log_snapshot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state — persists across Streamlit reruns in the same process
# ---------------------------------------------------------------------------
_scheduler: Optional[BackgroundScheduler] = None
_last_poll_time: Optional[datetime] = None
_last_poll_result: dict = {}   # {sport: n_games} from last successful poll
_poll_error_count: int = 0
_poll_errors: list = []        # last N error strings (capped at 10)
_db_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal poll job
# ---------------------------------------------------------------------------
def _poll_all_sports(db_path: Optional[str] = None) -> None:
    """
    Called by APScheduler every 5 minutes.
    Fetches all configured sports and writes to SQLite via log_snapshot().
    Errors are logged but never bubble up (APScheduler catches them anyway).
    """
    global _last_poll_time, _last_poll_result, _poll_error_count

    effective_db = db_path or _db_path
    results_summary: dict = {}

    try:
        raw = fetch_batch_odds()   # {sport_name: [game_dict, ...]}
        for sport, games in raw.items():
            if games:
                snapshots = log_snapshot(games, sport, effective_db)
                results_summary[sport] = len(snapshots)
            else:
                results_summary[sport] = 0

        _last_poll_time = datetime.now(timezone.utc)
        _last_poll_result = results_summary
        logger.info("Poll complete: %s", results_summary)

    except Exception as exc:  # noqa: BLE001
        _poll_error_count += 1
        err_str = f"{datetime.now(timezone.utc).isoformat()} — {exc}"
        _poll_errors.append(err_str)
        if len(_poll_errors) > 10:
            _poll_errors.pop(0)
        logger.error("Poll error #%d: %s", _poll_error_count, exc)


def _on_job_event(event) -> None:
    """Log APScheduler job events for observability."""
    if event.exception:
        logger.error("Job %s raised: %s", event.job_id, event.exception)
    else:
        logger.debug("Job %s executed OK", event.job_id)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def start_scheduler(
    db_path: Optional[str] = None,
    poll_interval_minutes: int = 5,
) -> None:
    """
    Start the background scheduler.

    Safe to call multiple times — returns immediately if already running.
    This is the Streamlit-friendly pattern: call once, guard with session_state.

    Args:
        db_path: Override default SQLite path (useful for testing).
        poll_interval_minutes: How often to poll. Default 5.
    """
    global _scheduler, _db_path

    if _scheduler is not None and _scheduler.running:
        logger.debug("Scheduler already running — skipping re-init")
        return

    _db_path = db_path
    init_db(db_path)   # Ensure schema exists before first poll

    _scheduler = BackgroundScheduler(
        job_defaults={"misfire_grace_time": 60},  # tolerate 1-min late fires
        timezone="UTC",
    )
    _scheduler.add_listener(_on_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    _scheduler.add_job(
        _poll_all_sports,
        trigger="interval",
        minutes=poll_interval_minutes,
        id="line_poll",
        replace_existing=True,
        kwargs={"db_path": db_path},
    )
    _scheduler.start()
    logger.info("Scheduler started (interval=%dm)", poll_interval_minutes)


def stop_scheduler() -> None:
    """
    Gracefully shut down the scheduler.
    Safe to call even if not running.
    """
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
    _scheduler = None


def trigger_poll_now(db_path: Optional[str] = None) -> dict:
    """
    Run an immediate poll outside the scheduled interval.
    Returns the result summary {sport: n_games}.
    Used by the UI "Refresh Now" button.

    Args:
        db_path: Optional path override.

    Returns:
        dict mapping sport name to number of game lines logged.
    """
    effective_db = db_path or _db_path
    _poll_all_sports(effective_db)
    return dict(_last_poll_result)


def get_status() -> dict:
    """
    Return scheduler observability state for the UI status bar.

    Returns:
        {
            "running": bool,
            "last_poll_time": datetime | None,
            "last_poll_result": {sport: n_games},
            "poll_error_count": int,
            "recent_errors": [str],
            "quota_report": str,
        }
    """
    return {
        "running": _scheduler is not None and _scheduler.running,
        "last_poll_time": _last_poll_time,
        "last_poll_result": dict(_last_poll_result),
        "poll_error_count": _poll_error_count,
        "recent_errors": list(_poll_errors),
        "quota_report": quota.report(),
    }


def is_running() -> bool:
    """Convenience predicate — True if scheduler is active."""
    return _scheduler is not None and _scheduler.running


def reset_state() -> None:
    """
    Reset all module-level state.
    Intended for testing only — never call from production code.
    """
    global _scheduler, _last_poll_time, _last_poll_result
    global _poll_error_count, _poll_errors, _db_path

    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)

    _scheduler = None
    _last_poll_time = None
    _last_poll_result = {}
    _poll_error_count = 0
    _poll_errors = []
    _db_path = None
