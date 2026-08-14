"""Splashsports team-pickem spread ingestion.

Splashsports renders its picksheet client-side (React); a plain HTTP GET only
returns the unhydrated shell, unlike the legacy officefootballpool.com scraper
that this replaces, which could log in and scrape server-rendered HTML with a
plain form POST. `fetch_splashsports_picksheet_html` therefore drives a real
browser session with Playwright. Parsing the resulting markup is kept as a
separate, pure function (`parse_splashsports_spreads`) so it can be tested
without a live browser or credentials.

Sign-in is gated by Google reCAPTCHA risk scoring. Filling and submitting the
form works fine on its own with correct credentials, but has been seen to
trip `INVALID_RECAPTCHA_ERROR` when a manual sign-in is active in another
session/tab at the same time. `fetch_splashsports_picksheet_html` therefore
prefers a saved session (from `login_and_save_splashsports_session` /
`nfl-ats splashsports-login`, where a human signs in by hand once) when one
exists, and falls back to filling the form with `SplashsportsCredentials`
otherwise.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from lxml import html as lxml_html

from nfl_ats.io import atomic_json, atomic_parquet, run_id
from nfl_ats.provenance import sha256_file

SIGN_IN_URL = "https://app.splashsports.com/sign-in?redirectTo=entries"
EMAIL_SELECTOR = '[data-test-id="dt.components.shared.auth.signIn.emailInput"]'
PASSWORD_SELECTOR = '[data-test-id="dt.components.shared.auth.passwordInput"]'
SUBMIT_SELECTOR = '[data-test-id="dt.components.shared.auth.signIn.submitButton"]'
CONTEST_CARD_SELECTOR = '[data-test-id="dt.common.components.contestCard"]'
ENTRIES_PAGE_SELECTOR = '[data-testid="my-entries-page"]'
FIRST_ENTRY_PICK_SELECTOR = '[data-testid^="entry-pick-"][data-testid$="-0"]'
PICKSHEET_PAGE_SELECTOR = '[data-testid="picksheet-page"]'

# How long a human has to complete sign-in (including any captcha challenge)
# in the window opened by `login_and_save_splashsports_session`.
LOGIN_TIMEOUT_MS = 300_000

# Splashsports team codes that differ from nflverse's standard abbreviations.
TEAM_CODE_OVERRIDES = {"JAC": "JAX"}

SPREAD_COLUMNS = (
    "observed_at_utc",
    "provider",
    "slate_label",
    "game_card_id",
    "team_id",
    "splashsports_team_code",
    "team_code",
    "spread_text",
    "team_spread",
)


@dataclass(frozen=True)
class SplashsportsCredentials:
    email: str
    password: str


@dataclass(frozen=True)
class SplashsportsSnapshot:
    snapshot_id: str
    root: Path
    html_path: Path
    spreads_path: Path
    manifest_path: Path


def credentials_from_environment() -> SplashsportsCredentials | None:
    email = os.environ.get("SPLASHSPORTS_EMAIL")
    password = os.environ.get("SPLASHSPORTS_PASSWORD")
    if not email or not password:
        return None
    return SplashsportsCredentials(email=email, password=password)


def _utc(instant: datetime | None) -> datetime:
    value = instant or datetime.now(UTC)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def normalize_team_code(splashsports_code: str) -> str:
    code = splashsports_code.strip().upper()
    return TEAM_CODE_OVERRIDES.get(code, code)


def _parse_spread(text: str) -> float | None:
    normalized = text.strip().upper()
    if not normalized or normalized == "TBD":
        return None
    if normalized in {"PK", "PICK", "PICK'EM"}:
        return 0.0
    try:
        return float(normalized)
    except ValueError:
        return None


def _launch_args(devtools: bool) -> list[str]:
    return ["--auto-open-devtools-for-tabs"] if devtools else []


def login_and_save_splashsports_session(
    state_path: Path,
    *,
    headless: bool = False,
    devtools: bool = False,
    timeout_ms: int = LOGIN_TIMEOUT_MS,
) -> None:
    """Open a browser for a human to sign in, then persist the session.

    Splashsports rejects an automated fill-and-submit of the sign-in form
    (reCAPTCHA scores it as bot traffic), so this waits for a human to
    complete the login themselves in the opened window — including whatever
    challenge Google presents — then saves the resulting cookies/local
    storage to `state_path` so later runs can skip the sign-in form entirely.
    `timeout_ms=0` waits indefinitely (Playwright's own convention), useful
    while debugging the page itself rather than the login.
    """

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:  # pragma: no cover - drives a real browser + human login
        browser = playwright.chromium.launch(
            headless=headless and not devtools, args=_launch_args(devtools)
        )
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(SIGN_IN_URL)
            print(f"Log in manually in the opened browser window: {SIGN_IN_URL}")
            wait_description = "indefinitely" if timeout_ms == 0 else f"up to {timeout_ms // 1000}s"
            print(f"Waiting {wait_description} for sign-in to complete...")
            page.wait_for_selector(CONTEST_CARD_SELECTOR, timeout=timeout_ms)
            state_path.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=state_path)
        finally:
            browser.close()


def fetch_splashsports_picksheet_html(
    *,
    credentials: SplashsportsCredentials | None = None,
    state_path: Path | None = None,
    headless: bool = True,
    devtools: bool = False,
    timeout_ms: int | None = None,
) -> str:
    """Log in and drive to the current week's picksheet, returning its rendered HTML.

    Prefers a saved session at `state_path` (from `login_and_save_splashsports_session`
    / `nfl-ats splashsports-login`) when one exists, since it skips the sign-in
    form entirely. Falls back to filling and submitting the form with
    `credentials` otherwise. `timeout_ms` bounds the wait for that sign-in to
    resolve (Playwright's own 30s default if left unset, 0 to wait forever) —
    the credential path can take longer than 30s if the site's reCAPTCHA is
    slow to clear.
    """

    use_saved_session = state_path is not None and state_path.is_file()
    if not use_saved_session and credentials is None:
        raise ValueError(
            "Provide splashsports credentials (SPLASHSPORTS_EMAIL/SPLASHSPORTS_PASSWORD) "
            "or a saved session; run `nfl-ats splashsports-login` to create one."
        )

    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:  # pragma: no cover - drives a real browser
        browser = playwright.chromium.launch(
            headless=headless and not devtools, args=_launch_args(devtools)
        )
        try:
            context = (
                browser.new_context(storage_state=str(state_path))
                if use_saved_session
                else browser.new_context()
            )
            page = context.new_page()
            page.goto(SIGN_IN_URL)

            if not use_saved_session and credentials is not None:
                page.fill(EMAIL_SELECTOR, credentials.email)
                page.fill(PASSWORD_SELECTOR, credentials.password)
                # Let whatever async work the form kicks off after typing (the
                # site's reCAPTCHA included) settle before submitting, rather
                # than racing it with a fixed sleep.
                page.wait_for_load_state("networkidle")
                page.click(SUBMIT_SELECTOR)

            try:
                # Post-login lands on the contests listing, not the per-contest
                # "my entries" page — that only exists after the card is clicked.
                page.wait_for_selector(CONTEST_CARD_SELECTOR, timeout=timeout_ms)
            except PlaywrightTimeoutError as error:
                if use_saved_session:
                    raise ValueError(
                        f"Saved splashsports session at {state_path} looks expired "
                        "or invalid. Run `nfl-ats splashsports-login` again."
                    ) from error
                raise

            page.click(CONTEST_CARD_SELECTOR)
            page.wait_for_selector(ENTRIES_PAGE_SELECTOR)

            page.locator(FIRST_ENTRY_PICK_SELECTOR).first.click()
            page.wait_for_selector(PICKSHEET_PAGE_SELECTOR)

            return page.content()  # type: ignore[no-any-return]
        finally:
            browser.close()


def parse_splashsports_spreads(
    page_html: str, *, observed_at: datetime | None = None
) -> pd.DataFrame:
    """Normalize a rendered picksheet page into one row per team spread.

    Each `team-row-{team_id}` button carries its own team's spread from that
    team's perspective (e.g. the favorite shows `-3.5`, the underdog `+3.5`),
    so no home/away assignment is needed here; that belongs to whatever join
    matches `team_code` against a schedule downstream.
    """

    observed = _utc(observed_at)
    tree = lxml_html.fromstring(page_html)
    slate_labels = tree.xpath(
        '//*[@data-testid="slate-tabs"]//button[@aria-selected="true"]'
        '//span[contains(@class, "font-bold")][1]/text()'
    )
    slate_label = slate_labels[0].strip() if slate_labels else None

    rows: list[dict[str, Any]] = []
    cards = tree.xpath('//*[starts-with(@data-testid, "game-pick-card-")]')
    for card in cards:
        game_card_id = card.get("data-testid").removeprefix("game-pick-card-")
        team_rows = card.xpath('.//*[starts-with(@data-testid, "team-row-")]')
        for team_row in team_rows:
            team_id = team_row.get("data-testid").removeprefix("team-row-")
            spread_nodes = team_row.xpath(f'.//*[@data-testid="team-spread-{team_id}"]')
            if not spread_nodes:
                continue
            spread_text = spread_nodes[0].text_content().strip()
            # The abbreviation span has no data-testid of its own; it is the
            # element immediately before the spread span in the same wrapper.
            abbreviation_nodes = spread_nodes[0].xpath("preceding-sibling::span[1]")
            splashsports_code = (
                abbreviation_nodes[0].text_content().strip() if abbreviation_nodes else ""
            )
            rows.append(
                {
                    "observed_at_utc": observed,
                    "provider": "splashsports",
                    "slate_label": slate_label,
                    "game_card_id": game_card_id,
                    "team_id": team_id,
                    "splashsports_team_code": splashsports_code,
                    "team_code": normalize_team_code(splashsports_code),
                    "spread_text": spread_text,
                    "team_spread": _parse_spread(spread_text),
                }
            )
    frame = pd.DataFrame(rows, columns=SPREAD_COLUMNS)
    frame["observed_at_utc"] = pd.to_datetime(frame["observed_at_utc"], utc=True)
    frame["team_spread"] = pd.to_numeric(frame["team_spread"], errors="coerce")
    return frame


def fetch_splashsports_spreads(
    *,
    credentials: SplashsportsCredentials | None = None,
    state_path: Path | None = None,
    headless: bool = True,
    devtools: bool = False,
    timeout_ms: int | None = None,
) -> pd.DataFrame:  # pragma: no cover - thin wrapper around a real-browser call
    page_html = fetch_splashsports_picksheet_html(
        credentials=credentials,
        state_path=state_path,
        headless=headless,
        devtools=devtools,
        timeout_ms=timeout_ms,
    )
    return parse_splashsports_spreads(page_html)


def write_splashsports_snapshot(
    page_html: str,
    spreads: pd.DataFrame,
    root: Path,
    *,
    observed_at: datetime,
) -> SplashsportsSnapshot:
    identifier = run_id(observed_at)
    destination = root / identifier
    if destination.exists():
        raise ValueError(f"Splashsports snapshot already exists: {destination}")
    destination.mkdir(parents=True)
    snapshot = SplashsportsSnapshot(
        snapshot_id=identifier,
        root=destination,
        html_path=destination / "picksheet.html",
        spreads_path=destination / "spreads.parquet",
        manifest_path=destination / "manifest.json",
    )
    temporary_html = snapshot.html_path.with_suffix(".html.tmp")
    temporary_html.write_text(page_html, encoding="utf-8")
    temporary_html.replace(snapshot.html_path)
    atomic_parquet(spreads, snapshot.spreads_path)
    manifest = {
        "schema_version": 1,
        "snapshot_id": identifier,
        "observed_at_utc": _utc(observed_at).isoformat(),
        "provider": "splashsports",
        "slate_label": (str(spreads["slate_label"].iloc[0]) if not spreads.empty else None),
        "files": {
            "picksheet.html": {
                "bytes": len(page_html.encode("utf-8")),
                "sha256": sha256_file(snapshot.html_path),
            },
            "spreads.parquet": {
                "rows": len(spreads),
                "sha256": sha256_file(snapshot.spreads_path),
            },
        },
    }
    atomic_json(manifest, snapshot.manifest_path)
    return snapshot
