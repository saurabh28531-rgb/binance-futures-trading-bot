import time
import httpx
from typing import Optional
from bot.config import config
from bot.logging_config import setup_logger

logger = setup_logger(__name__)

# Cache refreshes every 24 hours
CACHE_TTL_SECONDS = 24 * 60 * 60


class ExchangeCache:
    """
    Local in-memory cache of Binance Futures exchange structural rules.

    Fetches exchangeInfo once at startup and refreshes every 24 hours.
    All symbol and filter lookups are served from memory between refreshes.

    Structural rules cached (NOT market prices):
        - LOT_SIZE: min/max quantity and step size per symbol
        - PRICE_FILTER: min/max price bounds and tick size per symbol

    These are exchange-defined contract specifications that change
    rarely — but we refresh every 24 hours to stay current.

    Attributes:
        _symbols: Dictionary mapping symbol string to its filters
        _last_fetched: Unix timestamp of last successful fetch
    """

    def __init__(self) -> None:
        self._symbols: dict[str, dict] = {}
        self._last_fetched: float = 0.0

    def _is_stale(self) -> bool:
        """
        Check if cache has exceeded its TTL.

        Returns:
            True if cache needs refreshing, False if still valid
        """
        return (time.time() - self._last_fetched) > CACHE_TTL_SECONDS

    def _fetch_and_populate(self) -> None:
        """
        Fetch exchange info from Binance and repopulate cache.

        Makes exactly one unauthenticated API call.
        Called at startup and automatically when TTL expires.

        Raises:
            SystemExit: On startup failure — app cannot validate without data
        """
        url = f"{config.base_url}/fapi/v1/exchangeInfo"
        is_startup = self._last_fetched == 0.0

        logger.info(
            "Fetching exchange info from Binance"
            f"{'— startup' if is_startup else '— TTL refresh'}"
        )

        try:
            timeout = httpx.Timeout(
                connect=config.request_timeout_connect,
                read=config.request_timeout_read,
                write=config.request_timeout_connect,
                pool=config.request_timeout_connect
            )
            with httpx.Client(timeout=timeout) as client:
                response = client.get(url)
                response.raise_for_status()

            # Fix 1 — Safely parse JSON response
            try:
                data = response.json()
            except Exception:
                msg = "Binance returned malformed response for exchange info."
                logger.critical(msg) if is_startup else logger.warning(msg)
                if is_startup:
                    raise SystemExit(1)
                return

            # Fix 1 — Verify response is a dictionary
            if not isinstance(data, dict):
                msg = "Binance exchange info response has unexpected format."
                logger.critical(msg) if is_startup else logger.warning(msg)
                if is_startup:
                    raise SystemExit(1)
                return

        except httpx.TimeoutException:
            msg = (
                "Timed out fetching exchange info. "
                "Check your internet connection."
            )
            logger.critical(msg) if is_startup else logger.warning(msg)
            if is_startup:
                raise SystemExit(1)
            return

        except httpx.HTTPStatusError as e:
            msg = (
                f"Binance returned HTTP {e.response.status_code} "
                "while fetching exchange info."
            )
            logger.critical(msg) if is_startup else logger.warning(msg)
            if is_startup:
                raise SystemExit(1)
            return

        except httpx.RequestError as e:
            msg = f"Network error fetching exchange info: {e}"
            logger.critical(msg) if is_startup else logger.warning(msg)
            if is_startup:
                raise SystemExit(1)
            return

        # Parse and store symbol data
        new_symbols: dict[str, dict] = {}

        for symbol_data in data.get("symbols", []):
            symbol = symbol_data.get("symbol", "")
            status = symbol_data.get("status", "")
            contract_type = symbol_data.get("contractType", "")

            # Only cache actively trading perpetual contracts
            if status != "TRADING" or contract_type != "PERPETUAL":
                continue

            # Extract LOT_SIZE filter
            lot_size = None
            for f in symbol_data.get("filters", []):
                if f.get("filterType") == "LOT_SIZE":
                    lot_size = {
                        "min_qty": float(f["minQty"]),
                        "max_qty": float(f["maxQty"]),
                        "step_size": float(f["stepSize"])
                    }
                    break

            # Extract PRICE_FILTER
            price_filter = None
            for f in symbol_data.get("filters", []):
                if f.get("filterType") == "PRICE_FILTER":
                    price_filter = {
                        "min_price": float(f["minPrice"]),
                        "max_price": float(f["maxPrice"]),
                        "tick_size": float(f["tickSize"])
                    }
                    break

            new_symbols[symbol] = {
                "lot_size": lot_size,
                "price_filter": price_filter,
                "base_asset": symbol_data.get("baseAsset", ""),
                "quote_asset": symbol_data.get("quoteAsset", ""),
            }

        if not new_symbols:
            msg = "Exchange info returned no valid trading symbols."
            logger.critical(msg) if is_startup else logger.warning(msg)
            if is_startup:
                raise SystemExit(1)
            return

        # Atomic swap — replace old cache only after successful fetch
        self._symbols = new_symbols
        self._last_fetched = time.time()

        logger.info(
            f"Exchange cache ready — {len(new_symbols)} active "
            f"perpetual symbols loaded"
        )

    def initialize(self) -> None:
        """
        Initialize cache at application startup.

        Must be called once before any validation runs.
        Subsequent calls check TTL and refresh if stale.
        """
        if self._is_stale():
            self._fetch_and_populate()

    def _ensure_fresh(self) -> None:
        """
        Silently refresh cache if TTL has expired.

        Called before every cache lookup. If refresh fails,
        app continues with existing cached data and logs a warning.
        """
        if self._is_stale():
            logger.info("Exchange cache TTL expired — refreshing silently")
            self._fetch_and_populate()

    def is_valid_symbol(self, symbol: str) -> bool:
        """
        Check if symbol exists and is actively trading.

        Args:
            symbol: Uppercase trading pair e.g. 'BTCUSDT'

        Returns:
            True if symbol is valid, False otherwise
        """
        self._ensure_fresh()
        return symbol in self._symbols

    def get_lot_size(self, symbol: str) -> Optional[dict]:
        """
        Get LOT_SIZE filter rules for a symbol.

        Args:
            symbol: Uppercase trading pair e.g. 'BTCUSDT'

        Returns:
            Dictionary with min_qty, max_qty, step_size or None
        """
        self._ensure_fresh()
        return self._symbols.get(symbol, {}).get("lot_size")

    def get_price_filter(self, symbol: str) -> Optional[dict]:
        """
        Get PRICE_FILTER structural rules for a symbol.

        Note: These are exchange-defined contract specifications
        (tick size, price bounds) — NOT current market prices.

        Args:
            symbol: Uppercase trading pair e.g. 'BTCUSDT'

        Returns:
            Dictionary with min_price, max_price, tick_size or None
        """
        self._ensure_fresh()
        return self._symbols.get(symbol, {}).get("price_filter")

    def get_all_symbols(self) -> list[str]:
        """
        Get sorted list of all valid trading symbols.

        Returns:
            Sorted list of all active perpetual symbol strings
        """
        self._ensure_fresh()
        return sorted(self._symbols.keys())


# Single cache instance shared across the entire application
exchange_cache = ExchangeCache()