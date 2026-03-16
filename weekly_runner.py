from datetime import datetime, timedelta
import pandas as pd
import os
import yaml
from discord_notifier import DiscordNotifier
from github_publisher import GitHubPublisher


def load_config():
    with open("config.yml", "r") as f:
        return yaml.safe_load(f)


def run_weekly():
    config = load_config()
    print("Running weekly recap...")

    # Implementation for weekly summary logic
    # 1. Look at last 7 days of signal_log.csv
    # 2. Summarize PnL and trades
    # 3. Look at upcoming dividends for next 2 weeks

    # Placeholder for now
    discord = DiscordNotifier(os.environ.get("DISCORD_WEBHOOK_URL"))
    # discord.send_weekly_recap(...)
    print("Weekly recap complete (stub)")


if __name__ == "__main__":
    run_weekly()
