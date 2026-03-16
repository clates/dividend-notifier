import yfinance as yf
import pandas as pd
import numpy as np
import os
from datetime import timezone
from log_config import get_logger

log = get_logger("live_data_fetcher")


class LiveDataFetcher:
    def __init__(self, tickers, data_dir="state/data", min_market_cap_b=None):
        self.tickers = tickers
        self.data_dir = data_dir
        self.min_market_cap_b = min_market_cap_b
        os.makedirs(self.data_dir, exist_ok=True)
        log.debug(
            "LiveDataFetcher initialised: %d tickers, data_dir=%s, min_market_cap_b=%s",
            len(tickers),
            data_dir,
            min_market_cap_b,
        )

    # ------------------------------------------------------------------
    # Market cap filter
    # ------------------------------------------------------------------

    def _filter_by_market_cap(self, tickers):
        """
        Returns the subset of tickers whose current market cap meets or exceeds
        self.min_market_cap_b (in billions). Tickers that error out or have no
        market cap data are excluded with a warning.
        """
        threshold = self.min_market_cap_b * 1e9
        passed = []
        skipped_low = []
        skipped_no_data = []

        log.info(
            "Filtering %d tickers by market cap >= $%.0fB",
            len(tickers),
            self.min_market_cap_b,
        )
        for i, ticker in enumerate(tickers):
            try:
                mc = yf.Ticker(ticker).info.get("marketCap")
                if mc is None:
                    log.debug("%s: no marketCap in info — excluded", ticker)
                    skipped_no_data.append(ticker)
                elif mc >= threshold:
                    passed.append(ticker)
                else:
                    log.debug(
                        "%s: market cap $%.1fB < threshold — excluded",
                        ticker,
                        mc / 1e9,
                    )
                    skipped_low.append(ticker)
            except Exception as e:
                log.warning("%s: error fetching market cap (%s) — excluded", ticker, e)
                skipped_no_data.append(ticker)

            if (i + 1) % 50 == 0:
                log.info(
                    "Market cap filter progress: %d/%d (passed=%d)",
                    i + 1,
                    len(tickers),
                    len(passed),
                )

        log.info(
            "Market cap filter complete: %d passed, %d below threshold, %d no data",
            len(passed),
            len(skipped_low),
            len(skipped_no_data),
        )
        return passed

    # ------------------------------------------------------------------
    # Next ex-dividend date estimator
    # ------------------------------------------------------------------

    def _estimate_next_exdiv(self, ticker, historical_div_dates, calendar):
        """
        Returns a timezone-naive pd.Timestamp for the predicted next ex-dividend
        date, or None if we cannot make a reliable estimate.

        Strategy (hybrid):
          1. Compute the median interval between the last N historical ex-dates.
          2. Project forward from the most-recent ex-date using that interval.
          3. If Ticker.calendar contains a *future* Ex-Dividend Date, prefer it
             — it is the company's own announcement and more precise.
          4. Require at least 4 historical dates to trust the interval.
        """
        today = pd.Timestamp.now(tz="UTC").normalize()

        # --- Step 1: historical interval ---
        if len(historical_div_dates) < 4:
            log.debug(
                "%s: fewer than 4 historical div dates — skipping prediction", ticker
            )
            return None

        recent_dates = historical_div_dates[-8:]  # up to 8 most-recent dates
        gaps = [
            (recent_dates[i + 1] - recent_dates[i]).days
            for i in range(len(recent_dates) - 1)
        ]
        median_gap = int(np.median(gaps))

        # Sanity-check: only trust regular payers (gap between 20 and 200 days)
        if not (20 <= median_gap <= 200):
            log.debug(
                "%s: irregular interval (%dd) — skipping prediction", ticker, median_gap
            )
            return None

        last_exdiv = historical_div_dates[-1]
        # Normalise to UTC midnight so arithmetic is clean
        if last_exdiv.tzinfo is None:
            last_exdiv = last_exdiv.tz_localize("UTC")
        last_exdiv = last_exdiv.normalize()

        predicted = last_exdiv + pd.Timedelta(days=median_gap)

        # If the simple prediction is already in the past (e.g. we missed a cycle),
        # keep adding one interval until we land in the future.
        while predicted <= today:
            predicted = predicted + pd.Timedelta(days=median_gap)

        # --- Step 2: prefer calendar if it's a genuine future date ---
        cal_exdiv = None
        if isinstance(calendar, dict):
            raw = calendar.get("Ex-Dividend Date")
            if raw is not None:
                try:
                    cal_ts = pd.Timestamp(raw, tz="UTC").normalize()
                    if cal_ts > today:
                        cal_exdiv = cal_ts
                except Exception:
                    pass

        if cal_exdiv is not None:
            # Sanity-check: calendar date should be within 1 interval of our prediction
            delta = abs((cal_exdiv - predicted).days)
            if delta <= median_gap * 0.5:
                log.debug(
                    "%s: using calendar ex-div %s (predicted %s, Δ%dd)",
                    ticker,
                    cal_exdiv.date(),
                    predicted.date(),
                    delta,
                )
                return cal_exdiv.tz_localize(None)
            else:
                log.debug(
                    "%s: calendar ex-div %s diverges too far from prediction %s (Δ%dd) — using prediction",
                    ticker,
                    cal_exdiv.date(),
                    predicted.date(),
                    delta,
                )

        log.debug(
            "%s: predicted next ex-div %s (last=%s + %dd)",
            ticker,
            predicted.date(),
            last_exdiv.date(),
            median_gap,
        )
        return predicted.tz_localize(None)

    # ------------------------------------------------------------------
    # Main fetch
    # ------------------------------------------------------------------

    def fetch_all(self, period="90d"):
        """Fetches fresh data for all tickers and returns pivoted matrices."""
        tickers = self.tickers

        if self.min_market_cap_b is not None:
            tickers = self._filter_by_market_cap(tickers)

        log.info(
            "Fetching %s of data for %d tickers via yfinance", period, len(tickers)
        )

        all_prices = {}
        all_divs = {}
        # Map ticker -> predicted next ex-div Timestamp (tz-naive)
        predicted_next_exdivs = {}
        error_count = 0
        empty_count = 0

        for i, ticker in enumerate(tickers):
            try:
                t_obj = yf.Ticker(ticker)

                df = t_obj.history(
                    period=period,
                    interval="1d",
                    actions=True,
                    auto_adjust=False,
                )

                if df is None or df.empty:
                    log.debug("No data returned for %s (empty)", ticker)
                    empty_count += 1
                else:
                    # Flatten multi-index if present
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)

                    # Strip timezone from index so the rest of the pipeline stays
                    # timezone-naive (consistent with yf.download behaviour)
                    if df.index.tz is not None:
                        df.index = df.index.tz_localize(None)

                    df.to_parquet(os.path.join(self.data_dir, f"{ticker}.parquet"))
                    all_prices[ticker] = df["Close"]

                    if "Dividends" in df.columns:
                        div_count = int((df["Dividends"] > 0).sum())
                        if div_count > 0:
                            log.debug(
                                "%s: %d dividend events in window", ticker, div_count
                            )
                        all_divs[ticker] = df["Dividends"]

                    # --- Predict next ex-div date ---
                    all_historical = t_obj.dividends
                    if all_historical is not None and len(all_historical) >= 4:
                        calendar = {}
                        try:
                            calendar = t_obj.calendar or {}
                        except Exception:
                            pass
                        next_exdiv = self._estimate_next_exdiv(
                            ticker,
                            all_historical.index.tolist(),
                            calendar,
                        )
                        if next_exdiv is not None:
                            predicted_next_exdivs[ticker] = next_exdiv

            except Exception as e:
                log.warning("Error fetching %s: %s", ticker, e)
                error_count += 1

            if (i + 1) % 50 == 0:
                log.info(
                    "Progress: %d/%d tickers fetched (errors=%d, empty=%d)",
                    i + 1,
                    len(tickers),
                    error_count,
                    empty_count,
                )

        log.info(
            "Fetch complete: %d successful, %d empty, %d errors",
            len(all_prices),
            empty_count,
            error_count,
        )
        log.info(
            "Next ex-div estimated for %d/%d tickers",
            len(predicted_next_exdivs),
            len(all_prices),
        )

        log.info("Pivoting price and dividend data into matrices")
        price_matrix = pd.DataFrame(all_prices).ffill()
        div_matrix = pd.DataFrame(all_divs).reindex(price_matrix.index).fillna(0)
        log.info(
            "Matrices built: %d rows (trading days) × %d tickers",
            len(price_matrix),
            len(price_matrix.columns),
        )

        log.info("Calculating days-to-dividend and days-since-dividend indicators")
        to_div_matrix = pd.DataFrame(
            index=price_matrix.index, columns=price_matrix.columns, dtype=float
        ).fillna(999.0)
        since_div_matrix = pd.DataFrame(
            index=price_matrix.index, columns=price_matrix.columns, dtype=float
        ).fillna(999.0)

        tickers_with_divs = 0
        for t in div_matrix.columns:
            div_series = div_matrix[t]
            div_dates = div_series.index[div_series > 0].tolist()

            # Inject the predicted next ex-div as a synthetic future date so that
            # to_div_matrix correctly shows days-until for upcoming dividends that
            # fall beyond the historical fetch window.
            if t in predicted_next_exdivs:
                synthetic = predicted_next_exdivs[t]
                # Only add if it isn't already represented in historical data
                # (avoid double-counting a date that's already in the window)
                already_known = any(
                    abs((pd.Timestamp(d) - pd.Timestamp(synthetic)).days) < 5
                    for d in div_dates
                )
                if not already_known:
                    div_dates = div_dates + [pd.Timestamp(synthetic)]

            if not div_dates:
                continue

            tickers_with_divs += 1
            for d in div_dates:
                d_ts = pd.Timestamp(d)

                # Days Since (only for real past dates — not the synthetic future one)
                if d_ts <= price_matrix.index[-1]:
                    diff_since = (price_matrix.index - d_ts).days
                    mask_since = (diff_since >= 0) & (
                        diff_since < since_div_matrix[t].values
                    )
                    since_div_matrix.loc[mask_since, t] = diff_since[mask_since]

                # Days To
                diff_to = (d_ts - price_matrix.index).days
                mask_to = (diff_to >= 0) & (diff_to < to_div_matrix[t].values)
                to_div_matrix.loc[mask_to, t] = diff_to[mask_to]

        log.info(
            "Dividend indicators calculated: %d of %d tickers had dividend events",
            tickers_with_divs,
            len(div_matrix.columns),
        )

        # Summarise latest-day buy windows
        latest_row = to_div_matrix.iloc[-1]
        in_buy_window_35 = int((latest_row <= 35).sum())
        in_buy_window_7 = int((latest_row <= 7).sum())
        latest_date = price_matrix.index[-1] if len(price_matrix) > 0 else None
        log.info(
            "Latest day (%s): %d tickers in buy window (<=35d), %d imminent (<=7d)",
            latest_date.strftime("%Y-%m-%d") if latest_date is not None else "N/A",
            in_buy_window_35,
            in_buy_window_7,
        )

        return price_matrix, div_matrix, to_div_matrix, since_div_matrix


if __name__ == "__main__":
    fetcher = LiveDataFetcher(["AAPL", "MSFT", "T", "KO", "JNJ"])
    p, d, td, sd = fetcher.fetch_all()
    log.info("Price Matrix tail:\n%s", p.tail())
    today_row = td.iloc[-1]
    in_window = today_row[today_row <= 35].sort_values()
    log.info("Tickers in buy window today (<=35d):\n%s", in_window)
