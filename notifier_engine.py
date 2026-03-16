import pandas as pd
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
            self.state = {
                "cash": self.config["portfolio"]["initial_cash"],
                "holdings": {},  # {ticker: {shares, entry_price, entry_date, captured_dividends}}
                "initial_cash": self.config["portfolio"]["initial_cash"],
                "last_run": None,
            }
            self.save_state()

    def save_state(self):
        with open(self.portfolio_path, "w") as f:
            json.dump(self.state, f, indent=4)

    def log_action(
        self, date, ticker, action, price, shares, value, reason, pnl=None, div=None
    ):
        log_entry = {
            "Date": date.strftime("%Y-%m-%d"),
            "Ticker": ticker,
            "Action": action,
            "Price": round(price, 2),
            "Shares": shares,
            "Value": round(value, 2),
            "CashReserves": round(self.state["cash"], 2),
            "PricePnL": round(pnl, 2) if pnl is not None else None,
            "DivCaptured": round(div, 2) if div is not None else 0.0,
            "TotalPnL": round((pnl or 0) + (div or 0), 2)
            if (pnl is not None or div is not None)
            else None,
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
        Processes signals and updates virtual portfolio.
        Returns a list of actions taken for notification.
        """
        actions = []

        # 1. Collect Dividends
        for ticker, info in list(self.state["holdings"].items()):
            div_per_share = div_amount_row.get(ticker, 0)
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
                actions.append(f"💰 DIVIDEND: {ticker} paid ${dividend_received:.2f}")

        # 2. Process SELLS
        for ticker in signals.get("sell", []):
            if ticker in self.state["holdings"]:
                info = self.state["holdings"][ticker]
                # Apply slippage
                raw_price = price_row[ticker]
                price = raw_price * (1 - self.config["portfolio"]["slippage_pct"])

                shares = info["shares"]
                proceeds = shares * price

                pnl = (price - info["entry_price"]) * shares
                divs = info["captured_dividends"]

                self.state["cash"] += proceeds
                self.log_action(
                    current_date,
                    ticker,
                    "SELL",
                    price,
                    shares,
                    proceeds,
                    f"{self.config['strategy']['sell_after']} days post-div",
                    pnl=pnl,
                    div=divs,
                )

                del self.state["holdings"][ticker]
                actions.append(
                    f"🔴 SELL: {ticker} at ${price:.2f} (PnL: ${pnl + divs:.2f})"
                )

        # 3. Process BUYS
        current_equity = self.state["cash"] + sum(
            price_row.get(t, info["entry_price"]) * info["shares"]
            for t, info in self.state["holdings"].items()
        )

        max_pos = self.config["portfolio"]["max_positions"]
        pos_size_pct = self.config["portfolio"]["max_position_size_pct"]

        for ticker in signals.get("buy", []):
            if len(self.state["holdings"]) >= max_pos:
                break

            if ticker not in self.state["holdings"]:
                raw_price = price_row.get(ticker)
                if raw_price is None or np.isnan(raw_price):
                    continue

                # Apply slippage
                price = raw_price * (1 + self.config["portfolio"]["slippage_pct"])

                target_inv = current_equity * pos_size_pct
                actual_inv = min(target_inv, self.state["cash"])

                if actual_inv > price:
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
                        self.log_action(
                            current_date,
                            ticker,
                            "BUY",
                            price,
                            shares,
                            cost,
                            f"Div in {int(to_div_row[ticker])} days",
                        )
                        actions.append(
                            f"🟢 BUY: {ticker} at ${price:.2f} (Allocated ${cost:.2f})"
                        )

        self.state["last_run"] = current_date.strftime("%Y-%m-%d")
        self.save_state()
        return actions

    def get_portfolio_summary(self, current_prices):
        holdings_val = sum(
            current_prices.get(t, info["entry_price"]) * info["shares"]
            for t, info in self.state["holdings"].items()
        )
        total_val = self.state["cash"] + holdings_val
        return {
            "total_value": total_val,
            "cash": self.state["cash"],
            "holdings_count": len(self.state["holdings"]),
            "return_pct": (total_val / self.state["initial_cash"] - 1) * 100,
        }
