import os
import yaml
import pandas as pd
from datetime import datetime, timedelta
from live_data_fetcher import LiveDataFetcher
from notifier_engine import NotifierEngine
from discord_notifier import DiscordNotifier
from github_publisher import GitHubPublisher
from report_generator import ReportGenerator
from strategies.loyal_dividend_portfolio_strategy import LoyalDividendPortfolioStrategy
from log_config import get_logger

log = get_logger("weekly_runner")


def load_config():
    log.debug("Loading config.yml")
    with open("config.yml", "r") as f:
        config = yaml.safe_load(f)
    log.debug("Config loaded")
    return config


def run_weekly():
    log.info("=" * 60)
    log.info("WEEKLY RECAP STARTING — %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("=" * 60)

    config = load_config()

    today = datetime.today()
    week_start = (today - timedelta(days=6)).strftime("%Y-%m-%d")
    week_end = today.strftime("%Y-%m-%d")
    week_str = f"{week_start} → {week_end}"
    log.info("Week range: %s", week_str)

    # Read the signal log
    log_path = os.path.join("state", "signal_log.csv")
    if not os.path.exists(log_path):
        log.warning("No signal log found at %s — skipping weekly recap", log_path)
        return

    log.info("Reading signal log: %s", log_path)
    df = pd.read_csv(log_path)
    df["Date"] = pd.to_datetime(df["Date"])
    week_df = df[df["Date"] >= pd.to_datetime(week_start)]
    log.info(
        "Signal log loaded: %d total rows, %d rows in this week's window",
        len(df),
        len(week_df),
    )

    week_actions = {"buys": [], "sells": [], "dividends": []}

    for _, row in week_df.iterrows():
        if row["Action"] == "BUY":
            week_actions["buys"].append(
                {
                    "ticker": row["Ticker"],
                    "price": row["Price"],
                    "shares": row["Shares"],
                    "cost": row["Value"],
                }
            )
        elif row["Action"] == "SELL":
            week_actions["sells"].append(
                {
                    "ticker": row["Ticker"],
                    "total_pnl": row["TotalPnL"] if pd.notnull(row["TotalPnL"]) else 0,
                    "total_pnl_pct": (row["TotalPnL"] / row["Value"] * 100)
                    if pd.notnull(row["TotalPnL"])
                    else 0,
                }
            )
        elif row["Action"] == "DIVIDEND":
            week_actions["dividends"].append(
                {
                    "ticker": row["Ticker"],
                    "amount": row["DivCaptured"]
                    if pd.notnull(row["DivCaptured"])
                    else 0,
                    "per_share": row["Price"],
                    "shares": row["Shares"],
                }
            )

    log.info(
        "Week actions parsed — buys=%d, sells=%d, dividends=%d",
        len(week_actions["buys"]),
        len(week_actions["sells"]),
        len(week_actions["dividends"]),
    )

    # Fetch fresh data for upcoming preview
    log.info("Loading tickers from sp500_tickers.txt")
    with open("sp500_tickers.txt", "r") as f:
        tickers = [line.strip() for line in f if line.strip()]
    log.info("Loaded %d tickers", len(tickers))

    log.info("Fetching 60-day market data for weekly preview")
    min_cap = config["portfolio"].get("min_market_cap_b")
    fetcher = LiveDataFetcher(tickers, min_market_cap_b=min_cap)
    price_matrix, div_matrix, to_div_matrix, since_div_matrix = fetcher.fetch_all(
        period="60d"
    )

    latest_date = price_matrix.index[-1]
    row_prices = price_matrix.loc[latest_date]
    row_to_div = to_div_matrix.loc[latest_date]
    log.info("Using latest trading date: %s", latest_date)

    log.info("Initialising NotifierEngine for portfolio summary")
    engine = NotifierEngine(config)
    summary = engine.get_portfolio_summary(row_prices)
    log.info(
        "Portfolio summary: total=$%.2f, cash=$%.2f, positions=%d, return=%.2f%%",
        summary["total_value"],
        summary["cash"],
        summary["holdings_count"],
        summary["return_pct"],
    )

    strategy = LoyalDividendPortfolioStrategy(
        buy_before=config["strategy"]["buy_before"],
        sell_after=config["strategy"]["sell_after"],
    )
    log.debug("Strategy: %s", strategy.name)

    # Next week preview: dividends in 1-14 days
    next_week_preview = []
    preview_mask = (row_to_div > 0) & (row_to_div <= 14)
    for t in row_to_div[preview_mask].sort_values().index:
        days = int(row_to_div[t])
        in_holdings = (
            "held ✓" if t in engine.state["holdings"] else "opens entry window"
        )
        next_week_preview.append(f"**{t}** — div in {days}d · {in_holdings}")
    log.info(
        "Next-week preview: %d tickers with dividends in ≤14 days",
        len(next_week_preview),
    )

    log.info("Sending weekly recap to Discord")
    discord = DiscordNotifier(os.environ.get("DISCORD_WEBHOOK_URL"))
    discord.send_weekly_recap(week_str, summary, week_actions, next_week_preview)

    log.info("Generating weekly HTML report")
    generator = ReportGenerator()
    weekly_html = generator.generate_weekly_html(
        week_str, summary, week_actions, next_week_preview, log_path
    )
    log.info("Weekly HTML generated (%d bytes)", len(weekly_html))

    log.info("Publishing weekly HTML to GitHub Pages")
    publisher = GitHubPublisher(
        os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPO")
    )
    publisher.publish_file(
        f"{config['notifications']['github_pages_path']}weekly_recap.html",
        weekly_html,
        f"Weekly Recap: {week_str}",
    )

    log.info("=" * 60)
    log.info("WEEKLY RECAP COMPLETE for %s", week_str)
    log.info("=" * 60)


if __name__ == "__main__":
    run_weekly()
