"""Market & fundamental data providers (the 'auto' half of the hybrid model)."""

from stockscan.data.providers import (
    MarketSnapshot,
    DataProvider,
    YFinanceProvider,
    get_provider,
)

__all__ = [
    "MarketSnapshot",
    "DataProvider",
    "YFinanceProvider",
    "get_provider",
]
