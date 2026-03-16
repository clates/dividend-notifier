import json
import os
import yaml
import numpy as np
import pandas as pd
from datetime import datetime
from live_data_fetcher import LiveDataFetcher
from notifier_engine import NotifierEngine
from discord_notifier import DiscordNotifier
from github_publisher import GitHubPublisher
from report_generator import ReportGenerator
from strategies.loyal_dividend_portfolio_strategy import LoyalDividendPortfolioStrategy


def load_config():
    with open("config.yml", "r") as f:
        return yaml.safe_load(f)


def run_daily():
    config = load_config()
    print(f"Starting daily run at {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # 1. Load tickers
    with open("sp500_tickers.txt", "r") as f:
        tickers = [line.strip() for line in f if line.strip()]

    # 2. Fetch fresh 90-day data
    fetcher = LiveDataFetcher(tickers)
    price_matrix, div_matrix, to_div_matrix, since_div_matrix = fetcher.fetch_all(
        period="90d"
    )

    # 3. Today's row (most recent trading day)
    today = price_matrix.index[-1]
    row_prices = price_matrix.loc[today]
    row_to_div = to_div_matrix.loc[today]
    row_since_div = since_div_matrix.loc[today]
    row_div_amounts = div_matrix.loc[today]
    date_str = today.strftime("%Y-%m-%d")

    print(f"Running signals for {date_str}")

    # 4. Setup engine and strategy
    engine = NotifierEngine(config)
    strategy = LoyalDividendPortfolioStrategy(
        buy_before=config["strategy"]["buy_before"],
        sell_after=config["strategy"]["sell_after"],
    )

    # 5. Get signals
    signals = strategy.get_signals(
        today, set(engine.state["holdings"].keys()), row_to_div, row_since_div
    )

    # 6. Execute virtual trades
    actions = engine.execute_signals(
        today, signals, row_prices, row_to_div, row_div_amounts
    )

    # 7. Summary + upcoming
    summary = engine.get_portfolio_summary(row_prices)
    holdings_detail = engine.get_holdings_detail(row_prices)

    upcoming = []
    preview_mask = (row_to_div > 0) & (row_to_div <= 7)
    for t in row_to_div[preview_mask].sort_values().index:
        days = int(row_to_div[t])
        status = "held ✓" if t in engine.state["holdings"] else "not held"
        upcoming.append(f"{t} — {days} days away ({status})")

    # 8. Generate HTML report
    generator = ReportGenerator()
    html_content = generator.generate_daily_html(
        date_str, summary, actions, upcoming, engine.log_path, holdings_detail
    )

    # 9. Publish to GitHub Pages
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
        publisher.publish_file(
            f"{signal_path}signal_log.csv", log_csv, f"Signal Log: {date_str}"
        )

    # 10. Discord notification
    discord = DiscordNotifier(os.environ.get("DISCORD_WEBHOOK_URL"))
    discord.send_daily_signal(date_str, summary, actions, upcoming)

    print(
        f"Daily run complete. Portfolio value: ${summary['total_value']:,.2f} ({summary['return_pct']:+.2f}%)"
    )


if __name__ == "__main__":
    run_daily()
