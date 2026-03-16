# dividend-notifier

A Dockerized trading signal service that runs the **B35/S45 Loyal Dividend Capture Strategy** autonomously, maintaining its own virtual portfolio and broadcasting daily signals via Discord and GitHub Pages.

## What it does

Every weekday at **8:00 AM ET**, the service:

1. Downloads fresh 90-day price and dividend data for all S&P 500 tickers
2. Runs the `LoyalDividendPortfolioStrategy` against today's market data
3. Executes virtual trades and updates the internal portfolio state
4. Publishes a live HTML report to [GitHub Pages](https://clates.github.io/dividend-analysis/signal/)
5. Posts a formatted signal message to a Discord webhook

Every Saturday at **8:00 AM ET**, it posts a weekly recap with a forward-looking 14-day dividend calendar.

## Strategy

**Loyal Dividend Capture (B35/S45)**
- Buys any S&P 500 stock within **35 days before** its ex-dividend date
- Sells **45 days after** the ex-dividend date
- Includes a "Loyalty Rule": will not sell if the **next dividend is already within 35 days** (prevents unnecessary churn)
- Position sizing: **5% of total portfolio equity** per position, max **20 simultaneous positions**
- Slippage: **0.05%** per trade (realistic bid-ask spread simulation)

## Setup

### 1. Clone and configure

```bash
git clone https://github.com/clates/dividend-notifier.git
cd dividend-notifier
cp .env.example .env
# Edit .env with your tokens
```

### 2. Required environment variables

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
GITHUB_TOKEN=ghp_...              # Needs repo write access to dividend-analysis
GITHUB_REPO=clates/dividend-analysis
TZ=America/New_York
```

### 3. Run with Docker Compose

```bash
docker compose up -d
```

The container will start the internal scheduler and wait for the next 8:00 AM ET trigger.

### 4. Unraid Setup

In the Unraid Docker tab:

| Field | Value |
|:---|:---|
| Repository | `clates/dividend-notifier` |
| Volume | `/mnt/user/appdata/dividend-notifier/state` → `/app/state` |
| Env: `DISCORD_WEBHOOK_URL` | your webhook URL |
| Env: `GITHUB_TOKEN` | your Personal Access Token |
| Env: `GITHUB_REPO` | `clates/dividend-analysis` |
| Env: `TZ` | `America/New_York` |

### 5. Manual trigger (testing)

```bash
docker exec dividend-notifier python daily_runner.py    # Run daily logic now
docker exec dividend-notifier python weekly_runner.py   # Run weekly recap now
```

## File structure

```
dividend-notifier/
├── scheduler.py              # APScheduler entry point (container's CMD)
├── daily_runner.py           # Weekday signal logic
├── weekly_runner.py          # Saturday recap logic
├── live_data_fetcher.py      # yfinance 90-day data + indicator calc
├── notifier_engine.py        # Virtual portfolio execution + state management
├── discord_notifier.py       # Discord webhook message formatter
├── github_publisher.py       # GitHub API file publisher
├── report_generator.py       # HTML report builder (daily + weekly)
├── config.yml                # Non-secret config (strategy params, schedule)
├── sp500_tickers.txt         # Static S&P 500 ticker list (update quarterly)
├── strategies/               # Copied from dividend-analysis
└── state/                    # Docker volume — persisted on Unraid
    ├── portfolio_state.json  # Virtual portfolio (cash, holdings, history)
    ├── signal_log.csv        # Full trade history
    └── data/                 # Cached parquet files
```

## Disclaimer

This is a virtual portfolio for educational and research purposes only. It does not constitute financial advice. All signals represent what a mechanical algorithm would do — mirror them at your own discretion and risk.

The strategy was backtested on 10 years of S&P 500 data using unadjusted prices with a 0.05% slippage assumption. Past performance does not guarantee future results.
