import pandas as pd
import numpy as np
import json
import os
from datetime import datetime
from log_config import get_logger

log = get_logger("notifier_engine")


class NotifierEngine:
    def __init__(self, config, state_dir="state"):
        self.config = config
        self.state_dir = state_dir
        self.portfolio_path = os.path.join(self.state_dir, "portfolio_state.json")
        self.log_path = os.path.join(self.state_dir, "signal_log.csv")
        os.makedirs(self.state_dir, exist_ok=True)
        log.debug("NotifierEngine initialised: state_dir=%s", state_dir)
        self.load_state()

    def load_state(self):
        if os.path.exists(self.portfolio_path):
            with open(self.portfolio_path, "r") as f:
                self.state = json.load(f)
            log.info(
                "Portfolio state loaded: cash=$%.2f, holdings=%d, last_run=%s",
                self.state["cash"],
                len(self.state["holdings"]),
                self.state.get("last_run"),
            )
        else:
            initial = self.config["portfolio"]["initial_cash"]
            self.state = {
                "cash": initial,
                "holdings": {},
                "initial_cash": initial,
                "inception_date": datetime.today().strftime("%Y-%m-%d"),
                "last_run": None,
                "prev_buy_window": [],
            }
            log.info(
                "No existing state found — initialising fresh portfolio with $%.2f",
                initial,
            )
            self.save_state()

    def save_state(self):
        with open(self.portfolio_path, "w") as f:
            json.dump(self.state, f, indent=4, default=str)
        log.debug(
            "Portfolio state saved: cash=$%.2f, holdings=%d",
            self.state["cash"],
            len(self.state["holdings"]),
        )

    def log_action(
        self, date, ticker, action, price, shares, value, reason, pnl=None, div=None
    ):
        total_pnl = None
        if pnl is not None or div is not None:
            total_pnl = round((pnl or 0) + (div or 0), 2)

        log_entry = {
            "Date": date.strftime("%Y-%m-%d"),
            "Ticker": ticker,
            "Action": action,
            "Price": round(float(price), 2),
            "Shares": int(shares),
            "Value": round(float(value), 2),
            "CashReserves": round(float(self.state["cash"]), 2),
            "PricePnL": round(float(pnl), 2) if pnl is not None else None,
            "DivCaptured": round(float(div), 2) if div is not None else 0.0,
            "TotalPnL": total_pnl,
            "Reason": reason,
        }
        log.debug(
            "Logging action: %s %s @ $%.2f × %d shares = $%.2f | reason=%s",
            action,
            ticker,
            float(price),
            int(shares),
            float(value),
            reason,
        )
        df = pd.DataFrame([log_entry])
        if not os.path.exists(self.log_path):
            df.to_csv(self.log_path, index=False)
        else:
            df.to_csv(self.log_path, mode="a", header=False, index=False)

    def execute_signals(
        self, current_date, signals, price_row, to_div_row, div_amount_row
    ):
        """
        Processes signals for today and updates the virtual portfolio.
        Returns a list of human-readable action strings.
        """
        log.info(
            "Executing signals for %s — sell candidates: %d, buy candidates: %d",
            current_date,
            len(signals.get("sell", [])),
            len(signals.get("buy", [])),
        )

        buys = []
        sells = []
        dividends = []

        slippage = self.config["portfolio"]["slippage_pct"]
        max_pos = self.config["portfolio"]["max_positions"]
        pos_size_pct = self.config["portfolio"]["max_position_size_pct"]
        log.debug(
            "Config: slippage=%.4f%%, max_positions=%d, pos_size=%.1f%%",
            slippage * 100,
            max_pos,
            pos_size_pct * 100,
        )

        # 1. Collect Dividends first (before valuation)
        log.debug(
            "Checking %d held positions for dividend payments",
            len(self.state["holdings"]),
        )
        for ticker in list(self.state["holdings"].keys()):
            info = self.state["holdings"][ticker]
            div_per_share = float(div_amount_row.get(ticker, 0))
            if div_per_share > 0:
                dividend_received = div_per_share * info["shares"]
                self.state["cash"] += dividend_received
                info["captured_dividends"] += dividend_received
                log.info(
                    "DIVIDEND: %s — $%.4f/share × %d shares = $%.2f received (cash now $%.2f)",
                    ticker,
                    div_per_share,
                    info["shares"],
                    dividend_received,
                    self.state["cash"],
                )
                self.log_action(
                    current_date,
                    ticker,
                    "DIVIDEND",
                    div_per_share,
                    info["shares"],
                    dividend_received,
                    "Dividend Payment",
                    div=dividend_received,
                )
                dividends.append(
                    {
                        "ticker": ticker,
                        "amount": dividend_received,
                        "per_share": div_per_share,
                        "shares": info["shares"],
                    }
                )
            else:
                log.debug(
                    "  %s: no dividend today (div_per_share=%.4f)",
                    ticker,
                    div_per_share,
                )

        # 2. Current equity (for sizing)
        current_equity = self._calc_equity(price_row)
        log.debug("Current equity before sells: $%.2f", current_equity)

        # 3. Process SELLS
        log.info("Processing %d sell signals", len(signals.get("sell", [])))
        for ticker in signals.get("sell", []):
            if ticker in self.state["holdings"]:
                info = self.state["holdings"][ticker]
                raw_price = float(price_row.get(ticker, np.nan))
                if np.isnan(raw_price):
                    log.warning("SELL skipped: %s has no price data (NaN)", ticker)
                    continue
                price = raw_price * (1 - slippage)
                shares = info["shares"]
                proceeds = shares * price
                price_pnl = (price - info["entry_price"]) * shares
                captured_divs = info["captured_dividends"]
                total_pnl = price_pnl + captured_divs

                self.state["cash"] += proceeds
                log.info(
                    "SELL: %s — %d shares @ $%.2f = $%.2f proceeds | "
                    "price_pnl=$%.2f, divs_captured=$%.2f, total_pnl=$%.2f (%.1f%%)",
                    ticker,
                    shares,
                    price,
                    proceeds,
                    price_pnl,
                    captured_divs,
                    total_pnl,
                    (total_pnl / (info["entry_price"] * shares)) * 100,
                )
                self.log_action(
                    current_date,
                    ticker,
                    "SELL",
                    price,
                    shares,
                    proceeds,
                    f"{self.config['strategy']['sell_after']} days post-div",
                    pnl=price_pnl,
                    div=captured_divs,
                )
                del self.state["holdings"][ticker]
                sells.append(
                    {
                        "ticker": ticker,
                        "price": price,
                        "shares": shares,
                        "price_pnl": price_pnl,
                        "div_captured": captured_divs,
                        "total_pnl": total_pnl,
                        "total_pnl_pct": (total_pnl / (info["entry_price"] * shares))
                        * 100,
                    }
                )
            else:
                log.debug("SELL skipped: %s not in holdings", ticker)

        # 4. Process BUYS — recalc equity after sells
        current_equity = self._calc_equity(price_row)
        log.debug("Current equity after sells: $%.2f", current_equity)
        log.info(
            "Processing %d buy candidates (positions: %d/%d)",
            len(signals.get("buy", [])),
            len(self.state["holdings"]),
            max_pos,
        )

        for ticker in signals.get("buy", []):
            if len(self.state["holdings"]) >= max_pos:
                log.info("BUY skipped: max positions (%d) reached", max_pos)
                break
            if ticker in self.state["holdings"]:
                log.debug("BUY skipped: %s already held", ticker)
                continue

            raw_price = float(price_row.get(ticker, np.nan))
            if np.isnan(raw_price):
                log.warning("BUY skipped: %s has no price data (NaN)", ticker)
                continue

            price = raw_price * (1 + slippage)
            target_inv = current_equity * pos_size_pct
            actual_inv = min(target_inv, self.state["cash"])

            if actual_inv < price:
                log.warning(
                    "BUY skipped: %s — insufficient funds (need $%.2f, have $%.2f)",
                    ticker,
                    price,
                    actual_inv,
                )
                continue

            shares = int(actual_inv // price)
            if shares > 0:
                cost = shares * price
                self.state["cash"] -= cost
                days_to_div = int(to_div_row.get(ticker, 0))
                exdiv_date = (current_date + pd.Timedelta(days=days_to_div)).strftime(
                    "%Y-%m-%d"
                )
                self.state["holdings"][ticker] = {
                    "shares": shares,
                    "entry_price": price,
                    "entry_date": current_date.strftime("%Y-%m-%d"),
                    "exdiv_date": exdiv_date,
                    "captured_dividends": 0.0,
                }
            else:
                log.warning(
                    "BUY skipped: %s — 0 shares computable (price=$%.2f, available=$%.2f)",
                    ticker,
                    price,
                    actual_inv,
                )

        self.state["last_run"] = current_date.strftime("%Y-%m-%d")
        self.save_state()

        log.info(
            "Signal execution complete — buys=%d, sells=%d, dividends=%d",
            len(buys),
            len(sells),
            len(dividends),
        )
        return {"buys": buys, "sells": sells, "dividends": dividends}

    def compute_window_deltas(self, current_buy_window: list) -> dict:
        """
        Compares today's buy-window tickers against yesterday's persisted set.
        Returns:
            newly_entered  — tickers that entered the window today
            newly_exited   — tickers that left the window today (and aren't held)
        Also persists today's window so tomorrow can diff against it.
        """
        prev = set(self.state.get("prev_buy_window", []))
        curr = set(current_buy_window)

        newly_entered = sorted(curr - prev)
        newly_exited = sorted(prev - curr)

        log.info(
            "Window delta: +%d entered, -%d exited (prev=%d, curr=%d)",
            len(newly_entered),
            len(newly_exited),
            len(prev),
            len(curr),
        )
        if newly_entered:
            log.info("  Newly entered window: %s", newly_entered)
        if newly_exited:
            log.info("  Left window: %s", newly_exited)

        # Persist for tomorrow
        self.state["prev_buy_window"] = sorted(curr)
        self.save_state()

        return {"newly_entered": newly_entered, "newly_exited": newly_exited}

    def _calc_equity(self, price_row):
        holdings_val = sum(
            float(price_row.get(t, info["entry_price"])) * info["shares"]
            for t, info in self.state["holdings"].items()
        )
        total = self.state["cash"] + holdings_val
        log.debug(
            "_calc_equity: cash=$%.2f + holdings=$%.2f = total=$%.2f",
            self.state["cash"],
            holdings_val,
            total,
        )
        return total

    def get_portfolio_summary(self, price_row):
        total_value = self._calc_equity(price_row)
        initial = self.state["initial_cash"]
        summary = {
            "total_value": total_value,
            "cash": self.state["cash"],
            "holdings_count": len(self.state["holdings"]),
            "holdings_value": total_value - self.state["cash"],
            "return_pct": (total_value / initial - 1) * 100,
            "inception_date": self.state.get("inception_date", "N/A"),
            "initial_cash": initial,
        }
        log.debug("Portfolio summary: %s", summary)
        return summary

    def get_holdings_detail(self, price_row):
        """Returns a list of current holdings with unrealized PnL and exit window."""
        sell_after = self.config["strategy"]["sell_after"]
        detail = []
        for ticker, info in self.state["holdings"].items():
            current_price = float(price_row.get(ticker, info["entry_price"]))
            unrealized_pnl = (current_price - info["entry_price"]) * info["shares"]
            total_return = unrealized_pnl + info["captured_dividends"]

            exdiv_date = info.get("exdiv_date")
            expected_exit = None
            if exdiv_date:
                expected_exit = (
                    pd.Timestamp(exdiv_date) + pd.Timedelta(days=sell_after)
                ).strftime("%Y-%m-%d")

            log.debug(
                "  %s: entry=$%.2f, current=$%.2f, unrealized_pnl=$%.2f, "
                "exdiv=%s, expected_exit=%s",
                ticker,
                info["entry_price"],
                current_price,
                unrealized_pnl,
                exdiv_date,
                expected_exit,
            )
            detail.append(
                {
                    "ticker": ticker,
                    "shares": info["shares"],
                    "entry_price": info["entry_price"],
                    "current_price": current_price,
                    "entry_date": info["entry_date"],
                    "exdiv_date": exdiv_date,
                    "expected_exit": expected_exit,
                    "unrealized_pnl": unrealized_pnl,
                    "div_captured": info["captured_dividends"],
                    "total_return": total_return,
                }
            )
        return detail
