import yfinance as yf
import pandas as pd
import numpy as np
import os


class LiveDataFetcher:
    def __init__(self, tickers, data_dir="state/data"):
        self.tickers = tickers
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)

    def fetch_all(self, period="90d"):
        """Fetches fresh data for all tickers and returns pivoted matrices."""
        print(f"Fetching fresh data for {len(self.tickers)} tickers...")

        all_prices = {}
        all_divs = {}

        # We'll use yfinance to download in batches if possible, but individual is safer for dividends
        for i, ticker in enumerate(self.tickers):
            try:
                # yfinance download
                df = yf.download(
                    ticker,
                    period=period,
                    interval="1d",
                    progress=False,
                    actions=True,
                    auto_adjust=False,
                )
                if not df.empty:
                    # Flatten multi-index if present
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)

                    # Store
                    df.to_parquet(os.path.join(self.data_dir, f"{ticker}.parquet"))

                    all_prices[ticker] = df["Close"]
                    if "Dividends" in df.columns:
                        all_divs[ticker] = df["Dividends"]

                if (i + 1) % 50 == 0:
                    print(f"  Progress: {i + 1}/{len(self.tickers)}")
            except Exception as e:
                print(f"  Error fetching {ticker}: {e}")

        print("Pivoting data...")
        price_matrix = pd.DataFrame(all_prices).ffill()
        div_matrix = pd.DataFrame(all_divs).reindex(price_matrix.index).fillna(0)

        print("Calculating dividend indicators...")
        to_div_matrix = pd.DataFrame(
            index=price_matrix.index, columns=price_matrix.columns
        ).fillna(999.0)
        since_div_matrix = pd.DataFrame(
            index=price_matrix.index, columns=price_matrix.columns
        ).fillna(999.0)

        for t in div_matrix.columns:
            div_series = div_matrix[t]
            div_dates = div_series.index[div_series > 0]
            if not div_dates.empty:
                for d in div_dates:
                    # Days Since
                    diff_since = (price_matrix.index - d).days
                    mask_since = (diff_since >= 0) & (diff_since < since_div_matrix[t])
                    since_div_matrix.loc[mask_since, t] = diff_since[mask_since]

                    # Days To
                    diff_to = (d - price_matrix.index).days
                    mask_to = (diff_to >= 0) & (diff_to < to_div_matrix[t])
                    to_div_matrix.loc[mask_to, t] = diff_to[mask_to]

        return price_matrix, div_matrix, to_div_matrix, since_div_matrix


if __name__ == "__main__":
    # Test with a few tickers
    fetcher = LiveDataFetcher(["AAPL", "MSFT", "T"])
    p, d, td, sd = fetcher.fetch_all()
    print("Price Matrix Head:")
    print(p.tail())
    print("\nDays to Div (T):")
    print(td["T"].tail())
