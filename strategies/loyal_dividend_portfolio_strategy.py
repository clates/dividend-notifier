from strategies.base_portfolio_strategy import BasePortfolioStrategy
from log_config import get_logger

log = get_logger("strategy.loyal_dividend")


class LoyalDividendPortfolioStrategy(BasePortfolioStrategy):
    """
    Loyal Dividend Capture Strategy.

    Like DividendPortfolioStrategy but adds a "Loyalty Rule":
    If the next dividend for a currently held stock is already within
    the buy_before window, the engine does NOT sell — it stays loyal
    and holds through that next dividend cycle too.

    This prevents the "churn" pattern where the engine sells and
    immediately buys back the same stock on overlapping dividend windows.

    Buy:  Enter when days_to_div <= buy_before
    Sell: Exit when days_since_div >= sell_after
          BUT only if the next dividend is NOT within buy_before days
    """

    def __init__(self, buy_before: int = 30, sell_after: int = 30):
        super().__init__()
        self.buy_before = buy_before
        self.sell_after = sell_after
        self.name = f"Loyal Dividend Capture ({buy_before}/{sell_after})"
        self.description = (
            f"Buys {buy_before} days before ex-dividend date and sells {sell_after} days after. "
            f"Includes a Loyalty Rule: will not sell if the next dividend is already within {buy_before} days, "
            f"avoiding unnecessary churn on stocks with overlapping dividend windows."
        )
        log.debug(
            "Strategy initialised: buy_before=%d, sell_after=%d",
            buy_before,
            sell_after,
        )

    def get_signals(
        self,
        current_date,
        holdings: set,
        row_to_div,
        row_since_div,
    ) -> dict:
        """
        Returns sell_tickers and buy_tickers based on dividend proximity.
        """
        log.debug(
            "get_signals called: date=%s, holdings=%d tickers",
            current_date,
            len(holdings),
        )

        sell_tickers = []
        buy_tickers = []

        for t in holdings:
            days_since = row_since_div[t] if t in row_since_div else 999
            days_until_next = row_to_div[t] if t in row_to_div else 999

            # Loyalty Rule: hold if we are already in the next buy window
            if days_since >= self.sell_after and days_until_next > self.buy_before:
                log.debug(
                    "  SELL signal: %s (days_since=%s, days_until_next=%s)",
                    t,
                    days_since,
                    days_until_next,
                )
                sell_tickers.append(t)
            else:
                if days_since >= self.sell_after:
                    log.debug(
                        "  HOLD (loyalty rule): %s (days_since=%s, days_until_next=%s <= buy_before=%d)",
                        t,
                        days_since,
                        days_until_next,
                        self.buy_before,
                    )
                else:
                    log.debug(
                        "  HOLD (in window): %s (days_since=%s < sell_after=%d)",
                        t,
                        days_since,
                        self.sell_after,
                    )

        # Potential buys: not held AND within buy window
        potential_mask = (row_to_div > 0) & (row_to_div <= self.buy_before)
        for t in row_to_div[potential_mask].index:
            if t not in holdings:
                log.debug(
                    "  BUY signal: %s (days_to_div=%s)",
                    t,
                    row_to_div[t],
                )
                buy_tickers.append(t)

        log.info(
            "Signals: %d sells, %d buys (from %d holdings, %d candidates scanned)",
            len(sell_tickers),
            len(buy_tickers),
            len(holdings),
            int(potential_mask.sum()),
        )

        return {"sell": sell_tickers, "buy": buy_tickers}
