from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from nfl_ats.splashsports import (
    credentials_from_environment,
    normalize_team_code,
    parse_splashsports_spreads,
    write_splashsports_snapshot,
)

FIXTURE = Path(__file__).parent / "fixtures" / "splashsports_picksheet.html"

_CARD_TEMPLATE = """
<section data-testid="slate-tabs">
  <button aria-selected="true">
    <span class="flex"><span class="text-sm font-bold">Week 1</span></span>
  </button>
</section>
<article data-testid="game-pick-card-{game_id}">
  <div data-testid="winner-picks">
    <button data-testid="team-row-{home_id}">
      <span class="flex"><span class="truncate">{home_code}</span>
      <span data-testid="team-spread-{home_id}">{home_spread}</span>
      <span class="icons"></span></span>
    </button>
    <button data-testid="team-row-{away_id}">
      <span class="flex"><span class="truncate">{away_code}</span>
      <span data-testid="team-spread-{away_id}">{away_spread}</span>
      <span class="icons"></span></span>
    </button>
  </div>
</article>
"""


def _synthetic_page() -> str:
    return _CARD_TEMPLATE.format(
        game_id="g1",
        home_id="home-1",
        home_code="SEA",
        home_spread="-3.5",
        away_id="away-1",
        away_code="NE",
        away_spread="+3.5",
    )


def test_parse_splashsports_spreads_numeric_and_pk() -> None:
    page = _CARD_TEMPLATE.format(
        game_id="g1",
        home_id="home-1",
        home_code="SEA",
        home_spread="-3.5",
        away_id="away-1",
        away_code="NE",
        away_spread="+3.5",
    ) + _CARD_TEMPLATE.format(
        game_id="g2",
        home_id="home-2",
        home_code="JAC",
        home_spread="PK",
        away_id="away-2",
        away_code="CLE",
        away_spread="PK",
    )
    frame = parse_splashsports_spreads(page, observed_at=datetime(2026, 9, 8, tzinfo=UTC))

    assert len(frame) == 4
    assert (frame["slate_label"] == "Week 1").all()
    sea_row = frame.loc[frame["splashsports_team_code"].eq("SEA")].iloc[0]
    assert sea_row["team_spread"] == -3.5
    assert sea_row["team_code"] == "SEA"
    jac_row = frame.loc[frame["splashsports_team_code"].eq("JAC")].iloc[0]
    assert jac_row["team_spread"] == 0.0
    assert jac_row["team_code"] == "JAX"


def test_parse_splashsports_spreads_from_real_fixture() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    frame = parse_splashsports_spreads(html, observed_at=datetime(2026, 9, 1, tzinfo=UTC))

    assert len(frame) == 32
    assert frame["team_id"].nunique() == 32
    assert frame["slate_label"].iloc[0] == "Week 1"
    # Spreads had not posted yet when this page was captured.
    assert frame["team_spread"].isna().all()
    assert set(frame["team_code"]) >= {"NE", "SEA", "SF", "JAX"}


def test_normalize_team_code() -> None:
    assert normalize_team_code("jac") == "JAX"
    assert normalize_team_code("NE") == "NE"


def test_write_splashsports_snapshot(tmp_path: Path) -> None:
    page = _synthetic_page()
    observed_at = datetime(2026, 9, 8, tzinfo=UTC)
    spreads = parse_splashsports_spreads(page, observed_at=observed_at)

    snapshot = write_splashsports_snapshot(page, spreads, tmp_path / "raw", observed_at=observed_at)

    assert snapshot.html_path.read_text(encoding="utf-8") == page
    assert pd.read_parquet(snapshot.spreads_path).shape[0] == len(spreads)
    manifest = pd.read_json(snapshot.manifest_path, typ="series")
    assert manifest["provider"] == "splashsports"
    assert manifest["slate_label"] == "Week 1"


def test_write_splashsports_snapshot_rejects_duplicate(tmp_path: Path) -> None:
    page = _synthetic_page()
    observed_at = datetime(2026, 9, 8, tzinfo=UTC)
    spreads = parse_splashsports_spreads(page, observed_at=observed_at)
    root = tmp_path / "raw"
    write_splashsports_snapshot(page, spreads, root, observed_at=observed_at)

    with pytest.raises(ValueError, match="already exists"):
        write_splashsports_snapshot(page, spreads, root, observed_at=observed_at)


def test_parse_splashsports_spreads_handles_malformed_rows() -> None:
    page = """
    <article data-testid="game-pick-card-g1">
      <div data-testid="winner-picks">
        <button data-testid="team-row-missing-spread"><span>NE</span></button>
        <button data-testid="team-row-home-1">
          <span class="flex"><span class="truncate">SEA</span>
          <span data-testid="team-spread-home-1">not-a-number</span>
          <span class="icons"></span></span>
        </button>
      </div>
    </article>
    """
    frame = parse_splashsports_spreads(page, observed_at=datetime(2026, 9, 8, tzinfo=UTC))

    assert len(frame) == 1
    assert frame.iloc[0]["team_spread"] is None or pd.isna(frame.iloc[0]["team_spread"])
    assert frame.iloc[0]["slate_label"] is None


def test_credentials_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPLASHSPORTS_EMAIL", raising=False)
    monkeypatch.delenv("SPLASHSPORTS_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="SPLASHSPORTS_EMAIL"):
        credentials_from_environment()

    monkeypatch.setenv("SPLASHSPORTS_EMAIL", "user@example.com")
    monkeypatch.setenv("SPLASHSPORTS_PASSWORD", "hunter2")
    credentials = credentials_from_environment()
    assert credentials.email == "user@example.com"
    assert credentials.password == "hunter2"
