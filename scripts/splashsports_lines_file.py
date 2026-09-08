"""Build a ``pool-card-at-lines --lines-file`` CSV from a Splashsports snapshot.

``nfl-ats splashsports-ingest`` archives one row per team per game, each
carrying that team's own spread in ordinary sportsbook notation (the favorite
negative, e.g. Jaguars -8.5). ``pool-card-at-lines`` instead expects one row
per game with a single ``home_spread`` in this repo's own sign convention --
positive favors the home team (``nfl_ats.market_data`` negates every raw Odds
API home line to get there; ``tests/test_features.py::test_ats_target_sign_and_push``
pins the same convention for ``spread_line``). This script does that
conversion and the team-nickname-to-abbreviation join against the schedule,
and writes rows in the order Splashsports itself presented the games (its
picksheet order, not kickoff time), since that is the order picks get
compared against on the pool site.

Usage::

    uv run python scripts/splashsports_lines_file.py --season 2026 --week 1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
_SRC = REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Duplicated verbatim from scripts/movement_attribution.py's TEAM_NICKNAMES,
# per this repo's convention of not importing across scripts/*.py files.
# Splashsports' picksheet shows full nicknames ("Patriots"), not abbreviations.
TEAM_NICKNAMES: dict[str, str] = {
    "cardinals": "ARI",
    "falcons": "ATL",
    "ravens": "BAL",
    "bills": "BUF",
    "panthers": "CAR",
    "bears": "CHI",
    "bengals": "CIN",
    "browns": "CLE",
    "cowboys": "DAL",
    "broncos": "DEN",
    "lions": "DET",
    "packers": "GB",
    "texans": "HOU",
    "colts": "IND",
    "jaguars": "JAX",
    "chiefs": "KC",
    "rams": "LA",
    "chargers": "LAC",
    "raiders": "LV",
    "dolphins": "MIA",
    "vikings": "MIN",
    "patriots": "NE",
    "saints": "NO",
    "giants": "NYG",
    "jets": "NYJ",
    "eagles": "PHI",
    "steelers": "PIT",
    "seahawks": "SEA",
    "49ers": "SF",
    "buccaneers": "TB",
    "titans": "TEN",
    "commanders": "WAS",
}


def _latest(root: Path, glob: str) -> Path:
    candidates = sorted(root.glob(glob))
    if not candidates:
        raise FileNotFoundError(f"no snapshot matching {root / glob}")
    return candidates[-1]


def build_lines_file(*, season: int, week: int, destination: Path) -> pd.DataFrame:
    schedules_path = _latest(REPO / "data" / "raw", "*/schedules.parquet")
    schedules = pd.read_parquet(schedules_path)
    week_games = schedules[(schedules["season"] == season) & (schedules["week"] == week)]
    if week_games.empty:
        raise ValueError(f"no scheduled games for season={season} week={week} in {schedules_path}")

    spreads_path = _latest(REPO / "data" / "market" / "splashsports" / "raw", "*/spreads.parquet")
    spreads = pd.read_parquet(spreads_path).copy()
    spreads["abbr"] = spreads["team_code"].str.lower().map(TEAM_NICKNAMES)
    unmapped = spreads.loc[spreads["abbr"].isna(), "team_code"].unique()
    if len(unmapped):
        raise ValueError(f"unmapped Splashsports team code(s): {sorted(unmapped)}")

    # Splashsports' own picksheet order (first-seen game_card_id), not kickoff time.
    seen: list[str] = []
    for game_card_id in spreads["game_card_id"]:
        if game_card_id not in seen:
            seen.append(game_card_id)

    rows: list[dict[str, object]] = []
    for game_card_id in seen:
        card = spreads[spreads["game_card_id"] == game_card_id]
        abbrs = set(card["abbr"])
        match = week_games[
            week_games["home_team"].isin(abbrs) & week_games["away_team"].isin(abbrs)
        ]
        if match.empty:
            raise ValueError(
                f"Splashsports game card {game_card_id} ({abbrs}) matches no "
                f"scheduled season={season} week={week} game"
            )
        sched_row = match.iloc[0]
        home, away = sched_row["home_team"], sched_row["away_team"]
        # Splashsports spread is ordinary notation (favorite negative); this
        # repo's home_spread is the opposite (positive favors home).
        home_team_spread = float(card.loc[card["abbr"] == home, "team_spread"].iloc[0])
        rows.append(
            {
                "game_id": sched_row["game_id"],
                "home_team": home,
                "away_team": away,
                "home_spread": -home_team_spread,
            }
        )

    lines = pd.DataFrame(rows)
    destination.parent.mkdir(parents=True, exist_ok=True)
    lines.to_csv(destination, index=False)
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument(
        "--destination",
        type=Path,
        default=None,
        help="default: data/market/splashsports/lines_<season>_week<week>.csv",
    )
    args = parser.parse_args(argv)
    destination = args.destination or (
        REPO / "data" / "market" / "splashsports" / f"lines_{args.season}_week{args.week}.csv"
    )
    lines = build_lines_file(season=args.season, week=args.week, destination=destination)
    print(lines.to_string(index=False))
    print(f"\nwrote {len(lines)} rows to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
