from strategies.base_portfolio_strategy import BasePortfolioStrategy


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

    def get_signals(
        self,
        current_date,
        holdings: set,
        row_to_div,
        row_since_div,
    ) -> dict:
        """
        Returns sell_tickers and buy_tickers based on dividend proximity.

        Parameters
        ----------
        current_date : timestamp (unused here, available for subclasses)
        holdings : set of ticker strings currently held
        row_to_div : pd.Series  — days until next dividend per ticker
        row_since_div : pd.Series — days since last dividend per ticker

        Returns
        -------
        dict with keys "sell" and "buy", each a list of ticker strings.
        """
        sell_tickers = []
        buy_tickers = []

        for t in holdings:
            days_since = row_since_div[t] if t in row_since_div else 999
            days_until_next = row_to_div[t] if t in row_to_div else 999

            # Loyalty Rule: hold if we are already in the next buy window
            if days_since >= self.sell_after and days_until_next > self.buy_before:
                sell_tickers.append(t)

        # Potential buys: not held AND within buy window
        potential_mask = (row_to_div > 0) & (row_to_div <= self.buy_before)
        for t in row_to_div[potential_mask].index:
            if t not in holdings:
                buy_tickers.append(t)

        return {"sell": sell_tickers, "buy": buy_tickers}
