import pandas as pd


class BasePortfolioStrategy:
    """
    Base class for Portfolio-aware strategies.
    Unlike the previous version, this strategy looks at ALL tickers
    on a specific date and returns a list of desired actions.
    """

    def __init__(self):
        self.name = "Base Portfolio Strategy"
        self.description = "A base class for portfolio-wide signal generation."

    def compute_signals(self, current_date, market_data):
        """
        Overwrite this.
        market_data: Dictionary {ticker: DataFrame slice up to current_date}
        Returns: {
            'buy': [ticker1, ticker2, ...],
            'sell': [tickerA, tickerB, ...]
        }
        """
        return {"buy": [], "sell": []}
