from strategies.base_portfolio_strategy import BasePortfolioStrategy


class DividendPortfolioStrategy(BasePortfolioStrategy):
    """
    Pure Dividend Capture Strategy (no churn protection).

    Fires sell signal strictly when days_since_div >= sell_after, with
    no regard for whether the next dividend is approaching. This is the
    "baseline" version — useful for studying the raw effect of the timing
    window without the Loyalty Rule.

    Buy:  Enter when days_to_div <= buy_before
    Sell: Exit when days_since_div >= sell_after (no loyalty override)
    """

    def __init__(self, buy_before: int = 30, sell_after: int = 30):
        super().__init__()
        self.buy_before = buy_before
        self.sell_after = sell_after
        self.name = f"Dividend Capture Strategy ({buy_before}/{sell_after})"
        self.description = (
            f"Buys {buy_before} days before ex-dividend date and sells "
            f"{sell_after} days after. Pure timing — no loyalty override."
        )

    def get_signals(
        self,
        current_date,
        holdings: set,
        row_to_div,
        row_since_div,
    ) -> dict:
        sell_tickers = []
        buy_tickers = []

        for t in holdings:
            days_since = row_since_div[t] if t in row_since_div else 999
            if days_since >= self.sell_after:
                sell_tickers.append(t)

        potential_mask = (row_to_div > 0) & (row_to_div <= self.buy_before)
        for t in row_to_div[potential_mask].index:
            if t not in holdings:
                buy_tickers.append(t)

        return {"sell": sell_tickers, "buy": buy_tickers}
