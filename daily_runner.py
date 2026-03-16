import json
import os
import yaml
import numpy as np
import pandas as pd
from datetime import datetime
from live_data_fetcher import LiveDataFetcher
from notifier_engine import NotifierEngine
from discord_notifier import DiscordNotifier
from email_notifier import EmailNotifier
from github_publisher import GitHubPublisher
from report_generator import ReportGenerator
from strategies.loyal_dividend_portfolio_strategy import LoyalDividendPortfolioStrategy
from log_config import get_logger

log = get_logger("daily_runner")


def load_config():
    log.debug("Loading config.yml")
    with open("config.yml", "r") as f:
        config = yaml.safe_load(f)
    log.debug("Config loaded: %s", config)
    return config


def run_daily():
    log.info("=" * 60)
    log.info("DAILY RUN STARTING — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 60)

    config = load_config()

    # 1. Load tickers
    log.info("Step 1/10 — Loading tickers from sp500_tickers.txt")
    with open("sp500_tickers.txt", "r") as f:
        tickers = [line.strip() for line in f if line.strip()]
    log.info("Loaded %d tickers", len(tickers))

    # 2. Fetch fresh 90-day data
    log.info("Step 2/10 — Fetching 90-day market data")
    min_cap = config["portfolio"].get("min_market_cap_b")
    fetcher = LiveDataFetcher(tickers, min_market_cap_b=min_cap)
    price_matrix, div_matrix, to_div_matrix, since_div_matrix = fetcher.fetch_all(
        period="90d"
    )
    log.info(
        "Data fetched: %d tickers × %d trading days",
        len(price_matrix.columns),
        len(price_matrix),
    )

    # 3. Today's row (most recent trading day)
    log.info("Step 3/10 — Extracting most recent trading day")
    today = price_matrix.index[-1]
    row_prices = price_matrix.loc[today]
    row_to_div = to_div_matrix.loc[today]
    row_since_div = since_div_matrix.loc[today]
    row_div_amounts = div_matrix.loc[today]
    date_str = today.strftime("%Y-%m-%d")
    log.info("Most recent trading day: %s", date_str)

    # 4. Setup engine and strategy
    log.info("Step 4/10 — Initialising engine and strategy")
    engine = NotifierEngine(config)
    buy_before = config["strategy"]["buy_before"]
    sell_after = config["strategy"]["sell_after"]
    strategy = LoyalDividendPortfolioStrategy(
        buy_before=buy_before,
        sell_after=sell_after,
    )
    log.info(
        "Strategy: %s (buy_before=%d, sell_after=%d)",
        strategy.name,
        strategy.buy_before,
        strategy.sell_after,
    )
    log.info(
        "Portfolio state: cash=$%.2f, holdings=%d, last_run=%s",
        engine.state["cash"],
        len(engine.state["holdings"]),
        engine.state.get("last_run"),
    )
    if engine.state["holdings"]:
        log.info("Current holdings: %s", list(engine.state["holdings"].keys()))

    # 5. Get signals
    log.info("Step 5/10 — Generating signals")
    signals = strategy.get_signals(
        today, set(engine.state["holdings"].keys()), row_to_div, row_since_div
    )
    log.info(
        "Signals generated — buys: %d, sells: %d",
        len(signals.get("buy", [])),
        len(signals.get("sell", [])),
    )

    # Full current buy window (all tickers in window, held or not)
    buy_window_mask = (row_to_div > 0) & (row_to_div <= buy_before)
    current_buy_window = row_to_div[buy_window_mask].sort_values().index.tolist()
    log.info("Tickers currently in buy window: %d", len(current_buy_window))

    # 6. Execute virtual trades
    log.info("Step 6/10 — Executing virtual trades")
    actions = engine.execute_signals(
        today, signals, row_prices, row_to_div, row_div_amounts
    )
    log.info(
        "Trades executed — buys: %d, sells: %d, dividends: %d",
        len(actions["buys"]),
        len(actions["sells"]),
        len(actions["dividends"]),
    )

    # 7. Summary, holdings detail, window deltas, and upcoming
    log.info("Step 7/10 — Building portfolio summary and deltas")
    summary = engine.get_portfolio_summary(row_prices)
    holdings_detail = engine.get_holdings_detail(row_prices)
    log.info(
        "Portfolio: total=$%.2f, cash=$%.2f, positions=%d, return=%.2f%%",
        summary["total_value"],
        summary["cash"],
        summary["holdings_count"],
        summary["return_pct"],
    )

    # Delta: what changed in the buy window vs yesterday
    window_deltas = engine.compute_window_deltas(current_buy_window)

    # Watching: in buy window but not held (position limit reached or just not yet bought)
    watching = [
        {"ticker": t, "days_to_div": int(row_to_div[t])}
        for t in current_buy_window
        if t not in engine.state["holdings"]
    ]

    # Upcoming exdates in the next 14 days across the whole universe
    upcoming_mask = (row_to_div > 0) & (row_to_div <= 14)
    upcoming = []
    for t in row_to_div[upcoming_mask].sort_values().index:
        days = int(row_to_div[t])
        held = t in engine.state["holdings"]
        in_window = days <= buy_before
        upcoming.append(
            {
                "ticker": t,
                "days_to_div": days,
                "held": held,
                "in_window": in_window,
            }
        )
    log.info("Upcoming ex-dates (next 14 days): %d tickers", len(upcoming))

    # 8. Generate HTML report
    log.info("Step 8/10 — Generating HTML report")
    generator = ReportGenerator()
    html_content = generator.generate_daily_html(
        date_str, summary, actions, upcoming, engine.log_path, holdings_detail
    )
    log.info("HTML report generated (%d bytes)", len(html_content))

    # 9. Publish to GitHub Pages
    log.info("Step 9/10 — Publishing to GitHub Pages")
    publisher = GitHubPublisher(
        os.environ.get("GITHUB_TOKEN"),
        os.environ.get("GITHUB_REPO", "clates/dividend-analysis"),
    )
    signal_path = config["notifications"]["github_pages_path"]
    publisher.publish_file(
        f"{signal_path}index.html", html_content, f"Daily Signal: {date_str}"
    )

    if os.path.exists(engine.log_path):
        with open(engine.log_path, "r") as f:
            log_csv = f.read()
        log.info("Publishing signal log CSV (%d bytes)", len(log_csv))
        publisher.publish_file(
            f"{signal_path}signal_log.csv", log_csv, f"Signal Log: {date_str}"
        )
    else:
        log.warning(
            "Signal log not found at %s — skipping CSV publish", engine.log_path
        )

    # 10. Notifications — Discord + Email
    log.info("Step 10/10 — Sending notifications")
    shared_payload = dict(
        date_str=date_str,
        summary=summary,
        actions=actions,
        holdings_detail=holdings_detail,
        window_deltas=window_deltas,
        watching=watching,
        upcoming=upcoming,
        config=config,
    )

    discord = DiscordNotifier(os.environ.get("DISCORD_WEBHOOK_URL"))
    discord.send_daily_signal(**shared_payload)

    email = EmailNotifier()
    email.send_daily_signal(**shared_payload)

    log.info("=" * 60)
    log.info(
        "DAILY RUN COMPLETE — Portfolio: $%.2f (%+.2f%%)",
        summary["total_value"],
        summary["return_pct"],
    )
    log.info("=" * 60)


if __name__ == "__main__":
    run_daily()
