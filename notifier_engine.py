import pandas as pd
import numpy as np
import json
import os
from datetime import datetime


class NotifierEngine:
    def __init__(self, config, state_dir="state"):
        self.config = config
        self.state_dir = state_dir
        self.portfolio_path = os.path.join(self.state_dir, "portfolio_state.json")
        self.log_path = os.path.join(self.state_dir, "signal_log.csv")
        os.makedirs(self.state_dir, exist_ok=True)
        self.load_state()

    def load_state(self):
        if os.path.exists(self.portfolio_path):
            with open(self.portfolio_path, "r") as f:
                self.state = json.load(f)
        else:
            initial = self.config["portfolio"]["initial_cash"]
            self.state = {
                "cash": initial,
                "holdings": {},
                "initial_cash": initial,
                "inception_date": datetime.today().strftime("%Y-%m-%d"),
                "last_run": None,
            }
            self.save_state()

    def save_state(self):
        with open(self.portfolio_path, "w") as f:
            json.dump(self.state, f, indent=4, default=str)

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
        buys = []
        sells = []
        dividends = []

        slippage = self.config["portfolio"]["slippage_pct"]
        max_pos = self.config["portfolio"]["max_positions"]
        pos_size_pct = self.config["portfolio"]["max_position_size_pct"]

        # 1. Collect Dividends first (before valuation)
        for ticker in list(self.state["holdings"].keys()):
            info = self.state["holdings"][ticker]
            div_per_share = float(div_amount_row.get(ticker, 0))
            if div_per_share > 0:
                dividend_received = div_per_share * info["shares"]
                self.state["cash"] += dividend_received
                info["captured_dividends"] += dividend_received
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

        # 2. Current equity (for sizing)
        current_equity = self._calc_equity(price_row)

        # 3. Process SELLS
        for ticker in signals.get("sell", []):
            if ticker in self.state["holdings"]:
                info = self.state["holdings"][ticker]
                raw_price = float(price_row.get(ticker, np.nan))
                if np.isnan(raw_price):
                    continue
                price = raw_price * (1 - slippage)
                shares = info["shares"]
                proceeds = shares * price
                price_pnl = (price - info["entry_price"]) * shares
                captured_divs = info["captured_dividends"]
                total_pnl = price_pnl + captured_divs

                self.state["cash"] += proceeds
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

        # 4. Process BUYS
        # Recalc equity after sells
        current_equity = self._calc_equity(price_row)

        for ticker in signals.get("buy", []):
            if len(self.state["holdings"]) >= max_pos:
                break
            if ticker in self.state["holdings"]:
                continue

            raw_price = float(price_row.get(ticker, np.nan))
            if np.isnan(raw_price):
                continue

            price = raw_price * (1 + slippage)
            target_inv = current_equity * pos_size_pct
            actual_inv = min(target_inv, self.state["cash"])

            if actual_inv >= price:
                shares = int(actual_inv // price)
                if shares > 0:
                    cost = shares * price
                    self.state["cash"] -= cost
                    self.state["holdings"][ticker] = {
                        "shares": shares,
                        "entry_price": price,
                        "entry_date": current_date.strftime("%Y-%m-%d"),
                        "captured_dividends": 0.0,
                    }
                    days_to_div = int(to_div_row.get(ticker, 0))
                    self.log_action(
                        current_date,
                        ticker,
                        "BUY",
                        price,
                        shares,
                        cost,
                        f"Div in {days_to_div} days",
                    )
                    buys.append(
                        {
                            "ticker": ticker,
                            "price": price,
                            "shares": shares,
                            "cost": cost,
                            "days_to_div": days_to_div,
                            "alloc_pct": pos_size_pct * 100,
                        }
                    )

        self.state["last_run"] = current_date.strftime("%Y-%m-%d")
        self.save_state()

        return {"buys": buys, "sells": sells, "dividends": dividends}

    def _calc_equity(self, price_row):
        holdings_val = sum(
            float(price_row.get(t, info["entry_price"])) * info["shares"]
            for t, info in self.state["holdings"].items()
        )
        return self.state["cash"] + holdings_val

    def get_portfolio_summary(self, price_row):
        total_value = self._calc_equity(price_row)
        initial = self.state["initial_cash"]
        return {
            "total_value": total_value,
            "cash": self.state["cash"],
            "holdings_count": len(self.state["holdings"]),
            "holdings_value": total_value - self.state["cash"],
            "return_pct": (total_value / initial - 1) * 100,
            "inception_date": self.state.get("inception_date", "N/A"),
            "initial_cash": initial,
        }

    def get_holdings_detail(self, price_row):
        """Returns a list of current holdings with unrealized PnL."""
        detail = []
        for ticker, info in self.state["holdings"].items():
            current_price = float(price_row.get(ticker, info["entry_price"]))
            unrealized_pnl = (current_price - info["entry_price"]) * info["shares"]
            total_return = unrealized_pnl + info["captured_dividends"]
            detail.append(
                {
                    "ticker": ticker,
                    "shares": info["shares"],
                    "entry_price": info["entry_price"],
                    "current_price": current_price,
                    "entry_date": info["entry_date"],
                    "unrealized_pnl": unrealized_pnl,
                    "div_captured": info["captured_dividends"],
                    "total_return": total_return,
                }
            )
        return detail
