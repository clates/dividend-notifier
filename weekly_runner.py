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


def load_config():
    with open("config.yml", "r") as f:
        return yaml.safe_load(f)


def run_weekly():
    config = load_config()
    print("Running weekly recap...")

    today = datetime.today()
    week_start = (today - timedelta(days=6)).strftime("%Y-%m-%d")
    week_end = today.strftime("%Y-%m-%d")
    week_str = f"{week_start} → {week_end}"

    # Read the signal log
    log_path = os.path.join("state", "signal_log.csv")
    if not os.path.exists(log_path):
        print("No signal log found. Skipping weekly recap.")
        return

    df = pd.read_csv(log_path)
    df["Date"] = pd.to_datetime(df["Date"])
    week_df = df[df["Date"] >= pd.to_datetime(week_start)]

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

    # Fetch fresh data for upcoming preview
    with open("sp500_tickers.txt", "r") as f:
        tickers = [line.strip() for line in f if line.strip()]

    fetcher = LiveDataFetcher(tickers)
    price_matrix, div_matrix, to_div_matrix, since_div_matrix = fetcher.fetch_all(
        period="60d"
    )

    latest_date = price_matrix.index[-1]
    row_prices = price_matrix.loc[latest_date]
    row_to_div = to_div_matrix.loc[latest_date]

    engine = NotifierEngine(config)
    summary = engine.get_portfolio_summary(row_prices)

    strategy = LoyalDividendPortfolioStrategy(
        buy_before=config["strategy"]["buy_before"],
        sell_after=config["strategy"]["sell_after"],
    )

    # Next week preview: dividends in 1-14 days
    next_week_preview = []
    preview_mask = (row_to_div > 0) & (row_to_div <= 14)
    for t in row_to_div[preview_mask].sort_values().index:
        days = int(row_to_div[t])
        in_holdings = (
            "held ✓" if t in engine.state["holdings"] else "opens entry window"
        )
        next_week_preview.append(f"**{t}** — div in {days}d · {in_holdings}")

    discord = DiscordNotifier(os.environ.get("DISCORD_WEBHOOK_URL"))
    discord.send_weekly_recap(week_str, summary, week_actions, next_week_preview)

    # Generate weekly HTML page
    generator = ReportGenerator()
    weekly_html = generator.generate_weekly_html(
        week_str, summary, week_actions, next_week_preview, log_path
    )

    publisher = GitHubPublisher(
        os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPO")
    )
    publisher.publish_file(
        f"{config['notifications']['github_pages_path']}weekly_recap.html",
        weekly_html,
        f"Weekly Recap: {week_str}",
    )

    print(f"Weekly recap complete for {week_str}")


if __name__ == "__main__":
    run_weekly()
