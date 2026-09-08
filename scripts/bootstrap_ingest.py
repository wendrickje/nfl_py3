"""One-time bootstrap of the four raw snapshots ``weekly-run`` needs to refresh.

``weekly-run``'s own ingest step only refreshes a season range already covered
by an existing snapshot (``nfl_ats.weekly._ingest_step``); on an empty clone
there is nothing to refresh yet, so ``ingest``, ``pbp-ingest``,
``player-ingest`` and ``player-value-ingest`` each need one manual first run.
Deliberately excludes ``odds-backfill``: that only feeds ``opener-evaluation``
(the published card's cosmetic historical-accuracy headline), which
``pool-card-at-lines`` never reads, and it spends paid Odds API credits.

Usage::

    uv run python scripts/bootstrap_ingest.py
    uv run python scripts/bootstrap_ingest.py --start-season 2015 --end-season 2026 \\
        --stats-end-season 2025
"""

from __future__ import annotations

import argparse
import io
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_SRC = REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from nfl_ats import cli  # noqa: E402


def _run_step(name: str, argv: list[str]) -> None:
    print(f"=== {name}: {' '.join(argv)} ===", flush=True)
    started = time.monotonic()
    parser = cli.build_parser()
    args = parser.parse_args(argv)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        args.handler(args)
    elapsed = time.monotonic() - started
    print(buffer.getvalue().strip())
    print(f"--- {name} done in {elapsed:.1f}s ---\n", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start-season", type=int, default=2009)
    parser.add_argument(
        "--end-season",
        type=int,
        default=2026,
        help="last schedule season (schedules for the current season are known ahead of kickoff)",
    )
    parser.add_argument(
        "--stats-end-season",
        type=int,
        default=2025,
        help="last season with played games; applied to team stats, play-by-play, "
        "player, and player-value ingestion, all of which need games already played",
    )
    args = parser.parse_args(argv)

    steps = [
        (
            "ingest",
            [
                "ingest",
                "--start-season",
                str(args.start_season),
                "--end-season",
                str(args.end_season),
                "--stats-end-season",
                str(args.stats_end_season),
            ],
        ),
        (
            "pbp-ingest",
            [
                "pbp-ingest",
                "--start-season",
                str(args.start_season),
                "--end-season",
                str(args.stats_end_season),
            ],
        ),
        (
            "player-ingest",
            [
                "player-ingest",
                "--injury-start-season",
                str(args.start_season),
                "--injury-end-season",
                str(args.stats_end_season),
                "--roster-start-season",
                str(args.start_season),
                "--roster-end-season",
                str(args.stats_end_season),
                "--snap-start-season",
                str(args.start_season),
                "--snap-end-season",
                str(args.stats_end_season),
            ],
        ),
        (
            "player-value-ingest",
            [
                "player-value-ingest",
                "--start-season",
                str(args.start_season),
                "--end-season",
                str(args.stats_end_season),
            ],
        ),
    ]

    for name, step_argv in steps:
        try:
            _run_step(name, step_argv)
        except Exception as error:
            print(f"error: {name} failed: {error}", file=sys.stderr)
            return 1
    print("All four ingestions complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
