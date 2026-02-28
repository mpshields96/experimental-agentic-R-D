#!/usr/bin/env python3
"""
One-shot paper-bet scan — calls Odds API, finds Grade A/B bets, logs as paper bets.
Run manually: python3 scripts/paper_bet_scan.py

Usage notes:
- Costs ~15-20 Odds API credits for all active sports.
- Uses the same _auto_paper_bet_scan logic as the scheduler.
- Safe to run multiple times — bets are deduplicated by event_id+market+target.
"""

import sys
import os
import logging

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("paper_bet_scan")

from core.odds_fetcher import fetch_batch_odds, quota
from core.scheduler import _auto_paper_bet_scan
from core.line_logger import init_db, get_bets

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "line_history.db")

# Sports to scan — covers all in-season leagues today
SCAN_SPORTS = ["NBA", "NCAAB", "NHL", "EPL", "Bundesliga", "LaLiga", "Serie A", "Ligue 1", "MLS"]


def main() -> None:
    # Ensure event_id migration is applied
    init_db(DB_PATH)

    bets_before = len(get_bets(db_path=DB_PATH))
    logger.info("Paper-bet scan starting. Bets in log before: %d", bets_before)
    logger.info("Quota before scan: %s", quota.report())

    total_logged = 0
    total_games = 0

    games_dict = fetch_batch_odds(SCAN_SPORTS)

    logger.info("Quota after fetch: %s", quota.report())

    for sport, games in games_dict.items():
        if not games:
            continue
        total_games += len(games)
        logged = _auto_paper_bet_scan(games, sport, DB_PATH)
        total_logged += logged
        if logged:
            logger.info("  %s: %d new paper bet(s) logged from %d games", sport, logged, len(games))
        else:
            logger.info("  %s: no qualifying bets from %d games", sport, len(games))

    bets_after = len(get_bets(db_path=DB_PATH))
    logger.info(
        "Scan complete. Games processed: %d | New paper bets: %d | Total in log: %d",
        total_games, total_logged, bets_after,
    )
    logger.info("Final quota: %s", quota.report())


if __name__ == "__main__":
    main()
