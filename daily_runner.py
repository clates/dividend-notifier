import json
import os
import pandas as pd
from datetime import datetime
import yaml
from live_data_fetcher import LiveDataFetcher
from notifier_engine import NotifierEngine
from discord_notifier import DiscordNotifier
from github_publisher import GitHubPublisher
from report_generator import ReportGenerator


def load_config():
    with open("config.yml", "r") as f:
        return yaml.safe_load(f)


def run_daily():
    config = load_config()

    # Load tickers
    with open("sp500_tickers.txt", "r") as f:
        tickers = [line.strip() for line in f if line.strip()]

    # 1. Fetch Fresh Data (last 90 days)
    fetcher = LiveDataFetcher(tickers)
    price_matrix, div_matrix, to_div_matrix, since_div_matrix = fetcher.fetch_all(
        period="90d"
    )

    # 2. Setup Engine and Strategy
    engine = NotifierEngine(config)

    # Strategy parameters
    buy_before = config["strategy"]["buy_before"]
    sell_after = config["strategy"]["sell_after"]

    from strategies.loyal_dividend_portfolio_strategy import (
        LoyalDividendPortfolioStrategy,
    )

    strategy = LoyalDividendPortfolioStrategy(
        buy_before=buy_before, sell_after=sell_after
    )

    # Today's context
    today = price_matrix.index[-1]
    row_prices = price_matrix.loc[today]
    row_to_div = to_div_matrix.loc[today]
    row_since_div = since_div_matrix.loc[today]
    row_div_amounts = div_matrix.loc[today]

    # 3. Get Signals
    signals = strategy.get_signals(
        today, set(engine.state["holdings"].keys()), row_to_div, row_since_div
    )

    # 4. Execute and Log
    actions = engine.execute_signals(
        today, signals, row_prices, row_to_div, row_div_amounts
    )

    # 5. Get Upcoming Preview (next 7 days)
    upcoming = []
    potential_mask = (row_to_div > 0) & (row_to_div <= 7)
    for t in row_to_div[potential_mask].index:
        days = int(row_to_div[t])
        status = "held ✓" if t in engine.state["holdings"] else "not held"
        upcoming.append(f"{t} → {days} days away ({status})")

    summary = engine.get_portfolio_summary(row_prices)
    date_str = today.strftime("%Y-%m-%d")

    # 6. Generate and Publish Report
    generator = ReportGenerator()
    html_content = generator.generate_daily_html(
        date_str, summary, actions, upcoming, engine.log_path
    )

    publisher = GitHubPublisher(
        os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPO")
    )
    publisher.publish_file(
        f"{config['notifications']['github_pages_path']}index.html",
        html_content,
        f"Daily Signal Update: {date_str}",
    )

    # Also publish the full log
    with open(engine.log_path, "r") as f:
        log_csv = f.read()
    publisher.publish_file(
        f"{config['notifications']['github_pages_path']}signal_log.csv",
        log_csv,
        f"Update Signal Log: {date_str}",
    )

    # 7. Notify Discord
    discord = DiscordNotifier(os.environ.get("DISCORD_WEBHOOK_URL"))
    discord.send_daily_signal(date_str, summary, actions, upcoming)

    print(f"Daily run complete for {date_str}")


if __name__ == "__main__":
    run_daily()
