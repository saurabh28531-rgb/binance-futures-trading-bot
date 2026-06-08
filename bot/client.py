import hashlib
import hmac
import time
from typing import Optional
from urllib.parse import urlencode

import httpx

from bot.config import config
from bot.logging_config import setup_logger

logger = setup_logger(__name__)


class BinanceAPIError(Exception):
    """
    Raised when Binance API returns an error response.

    Attributes:
        code: Binance error code e.g. -1121
        message: Human readable translated error message
        raw_message: Original message from Binance
    """

    ERROR_MAP = {
        -1000: "An unknown error occurred. Please try again.",
        -1001: "Connection interrupted. Please try again.",
        -1002: "Authentication failed. Check your API key and secret.",
        -1003: "Too many requests. Please slow down.",
        -1006: "Unexpected response from Binance. Please try again.",
        -1007: "Request timed out waiting for response from Binance.",
        -1013: "Order size too small. Check minimum quantity for this symbol.",
        -1015: "Too many orders placed. Please wait before placing more.",
        -1021: "Request timestamp out of sync. Check your system clock.",
        -1022: "Invalid signature. Check your API secret key.",
        -1100: "Invalid characters in one or more parameters.",
        -1101: "Too many parameters in request.",
        -1102: "A required parameter is missing.",
        -1103: "Unknown parameter sent in request.",
        -1104: "Not all parameters were read by the server.",
        -1105: "A required parameter is empty.",
        -1106: "Parameter not required for this request.",
        -1111: "Quantity has too many decimal places for this symbol.",
        -1112: "No open orders found for this symbol.",
        -1114: "Time in force cannot be used with this order type.",
        -1115: "Invalid time in force value.",
        -1116: "Invalid order type.",
        -1117: "Invalid order side. Must be BUY or SELL.",
        -1118: "New client order ID is empty.",
        -1121: "Invalid symbol. Please check the symbol and try again.",
        -1125: "Listen key does not exist.",
        -2010: "Insufficient balance to place this order.",
        -2011: "Order not found for cancellation.",
        -2013: "Order not found.",
        -2014: "API key format is invalid.",
        -2015: "Invalid API key, IP address, or permissions.",
        -2018: "Insufficient balance for margin.",
        -2019: "Insufficient balance for position.",
        -4003: "Quantity is below the minimum allowed for this symbol.",
        -4004: "Price is below the minimum allowed for this symbol.",
        -4005: "Maximum open order limit reached for this symbol.",
        -4008: "Invalid trigger price.",
        -4014: "Price too high — exceeds maximum allowed for this symbol.",
        -4029: "Invalid tick size for price.",
        -4030: "Invalid step size for quantity.",
    }

    def __init__(self, code: int, raw_message: str) -> None:
        self.code = code
        self.raw_message = raw_message
        self.message = self.ERROR_MAP.get(
            code,
            f"Binance error {code}: {raw_message}"
        )
        super().__init__(self.message)


class NetworkError(Exception):
    """
    Raised when a network level failure occurs.
    Separate from API errors — these are connectivity issues.
    """
    pass


class BinanceClient:
    """
    Authenticated HTTP client for Binance Futures Demo API.

    Handles:
        - HMAC-SHA256 request signing
        - Timestamp injection
        - Timeouts on every request
        - Retry with exponential backoff on transient failures
        - Request ID injection for log traceability
        - Safe logging — credentials never appear in logs

    All private endpoints require signature. Public endpoints
    like exchangeInfo are called directly without this client.
    """

    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(self) -> None:
        self._timeout = httpx.Timeout(
            connect=config.request_timeout_connect,
            read=config.request_timeout_read,
	    write=config.request_timeout_connect,
    	    pool=config.request_timeout_connect
        )

    def _sign(self, params: dict) -> dict:
        """
        Add timestamp and HMAC-SHA256 signature to request parameters.

        Binance requires every authenticated request to include:
            - timestamp: current Unix time in milliseconds
            - signature: HMAC-SHA256 of the query string using secret key

        The secret key is used here but NEVER logged or stored in params.

        Args:
            params: Request parameters dictionary

        Returns:
            Parameters dictionary with timestamp and signature added
        """
        params["timestamp"] = int(time.time() * 1000)
        query_string = urlencode(params)
        signature = hmac.new(
            config.secret_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def _get_headers(self) -> dict:
        """
        Build request headers with API key.

        API key goes in header — never in URL or logged.

        Returns:
            Headers dictionary with X-MBX-APIKEY set
        """
        return {
            "X-MBX-APIKEY": config.api_key,
            "Content-Type": "application/x-www-form-urlencoded"
        }

    def _post(
        self,
        endpoint: str,
        params: dict,
        request_id: str
    ) -> dict:
        """
        Execute a signed POST request with retry and exponential backoff.

        Retries on transient failures (429, 5xx, network errors).
        Does not retry on client errors (4xx) — these are permanent.

        Args:
            endpoint: API endpoint path e.g. '/fapi/v1/order'
            params: Request parameters that will be signed
            request_id: Unique ID for log traceability

        Returns:
            Parsed JSON response dictionary

        Raises:
            BinanceAPIError: On API level errors from Binance
            NetworkError: On unrecoverable network failures
        """
        url = f"{config.base_url}{endpoint}"
        signed_params = self._sign(params.copy())
        headers = self._get_headers()

        safe_params = {
            k: v for k, v in params.items()
            if k not in ("signature", "timestamp")
        }
        logger.debug(
            f"POST {endpoint} | params={safe_params}",
            extra={"request_id": request_id}
        )

        last_exception: Optional[Exception] = None

        for attempt in range(1, config.max_retries + 1):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(
                        url,
                        data=signed_params,
                        headers=headers
                    )

                logger.debug(
                    f"POST {endpoint} → HTTP {response.status_code}",
                    extra={"request_id": request_id}
                )

                response_data = response.json()

                if response.status_code != 200:
                    error_code = response_data.get("code", -1)
                    error_msg = response_data.get("msg", "Unknown error")

                    if response.status_code not in self.RETRYABLE_STATUS_CODES:
                        logger.error(
                            f"Binance API error {error_code}: {error_msg}",
                            extra={"request_id": request_id}
                        )
                        raise BinanceAPIError(error_code, error_msg)

                    logger.warning(
                        f"Retryable HTTP {response.status_code} on attempt "
                        f"{attempt}/{config.max_retries}",
                        extra={"request_id": request_id}
                    )
                    last_exception = BinanceAPIError(error_code, error_msg)

                else:
                    logger.debug(
                        "Response received successfully",
                        extra={"request_id": request_id}
                    )
                    return response_data

            except httpx.TimeoutException:
                logger.warning(
                    f"Request timed out on attempt {attempt}/{config.max_retries}",
                    extra={"request_id": request_id}
                )
                last_exception = NetworkError(
                    "Request timed out. Check your internet connection."
                )

            except httpx.RequestError as e:
                logger.warning(
                    f"Network error on attempt {attempt}/{config.max_retries}: {e}",
                    extra={"request_id": request_id}
                )
                last_exception = NetworkError(
                    f"Network error: {e}. Check your internet connection."
                )

            if attempt < config.max_retries:
                wait_seconds = 2 ** (attempt - 1)
                logger.info(
                    f"Waiting {wait_seconds}s before retry...",
                    extra={"request_id": request_id}
                )
                time.sleep(wait_seconds)

        logger.error(
            f"All {config.max_retries} attempts failed for POST {endpoint}",
            extra={"request_id": request_id}
        )
        raise last_exception

    def place_order(self, params: dict, request_id: str) -> dict:
        """
        Place a futures order on Binance.

        Args:
            params: Validated order parameters from orders.py
            request_id: Unique ID for log traceability

        Returns:
            Parsed order response from Binance

        Raises:
            BinanceAPIError: On API rejection
            NetworkError: On network failure
        """
        return self._post("/fapi/v1/order", params, request_id)


# Single client instance shared across the application
binance_client = BinanceClient()