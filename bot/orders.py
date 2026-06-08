import uuid
from dataclasses import dataclass
from typing import Optional

from bot.client import BinanceAPIError, NetworkError, binance_client
from bot.logging_config import setup_logger

logger = setup_logger(__name__)


@dataclass
class OrderResult:
    """
    Structured representation of a successfully placed order.

    Attributes:
        order_id: Unique order ID assigned by Binance
        symbol: Trading pair e.g. 'BTCUSDT'
        side: Order side 'BUY' or 'SELL'
        order_type: 'MARKET' or 'LIMIT'
        status: Order status from Binance e.g. 'NEW', 'FILLED'
        quantity: Requested order quantity
        executed_qty: Quantity actually executed so far
        avg_price: Average execution price, None if not yet filled
        price: Limit price, None for MARKET orders
        request_id: Internal request ID for log traceability
    """
    order_id: int
    symbol: str
    side: str
    order_type: str
    status: str
    quantity: float
    executed_qty: float
    avg_price: Optional[float]
    price: Optional[float]
    request_id: str


@dataclass
class OrderError:
    """
    Structured representation of a failed order attempt.

    Attributes:
        reason: Plain English explanation of what went wrong
        request_id: Internal request ID for log traceability
    """
    reason: str
    request_id: str


def _parse_order_response(
    response: dict,
    request_id: str
) -> OrderResult:
    """
    Parse raw Binance order response into structured OrderResult.

    Handles missing or zero values gracefully — Binance does not always
    return all fields depending on order status.

    Args:
        response: Raw JSON response dictionary from Binance
        request_id: Request ID for traceability

    Returns:
        Populated OrderResult dataclass instance

    Raises:
        KeyError: If a required field is missing from response
    """
    # avgPrice is '0' for unfilled orders — treat as None
    raw_avg_price = response.get("avgPrice", "0")
    avg_price = float(raw_avg_price) if float(raw_avg_price) > 0 else None

    # price is '0' for MARKET orders — treat as None
    raw_price = response.get("price", "0")
    price = float(raw_price) if float(raw_price) > 0 else None

    return OrderResult(
        order_id=int(response["orderId"]),
        symbol=response["symbol"],
        side=response["side"],
        order_type=response["type"],
        status=response["status"],
        quantity=float(response["origQty"]),
        executed_qty=float(response.get("executedQty", "0")),
        avg_price=avg_price,
        price=price,
        request_id=request_id
    )


def _build_order_params(
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: Optional[float]
) -> dict:
    """
    Build Binance API parameter payload for an order.

    MARKET orders: symbol, side, type, quantity
    LIMIT orders: symbol, side, type, quantity, price, timeInForce

    timeInForce GTC (Good Till Cancelled) is the standard for LIMIT orders —
    order stays open until filled or manually cancelled.

    Args:
        symbol: Validated trading pair e.g. 'BTCUSDT'
        side: Validated 'BUY' or 'SELL'
        order_type: Validated 'MARKET' or 'LIMIT'
        quantity: Validated quantity float
        price: Validated price float or None for MARKET

    Returns:
        Parameters dictionary ready for signing and sending
    """
    params = {
        "symbol": symbol,
        "side": side,
        "type": order_type,
        "quantity": quantity,
    }

    if order_type == "LIMIT":
        params["price"] = price
        params["timeInForce"] = "GTC"

    return params


def place_order(
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: Optional[float] = None
) -> OrderResult | OrderError:
    """
    Place a MARKET or LIMIT futures order on Binance Demo Trading.

    Generates a unique request ID for full log traceability.
    Builds, signs, and sends the order via BinanceClient.
    Returns structured result or structured error — never raises.

    Args:
        symbol: Validated trading pair e.g. 'BTCUSDT'
        side: Validated 'BUY' or 'SELL'
        order_type: Validated 'MARKET' or 'LIMIT'
        quantity: Validated quantity float
        price: Validated price float or None for MARKET orders

    Returns:
        OrderResult on success
        OrderError on any failure — with plain English reason
    """
    # Generate unique request ID for this order's full lifecycle
    request_id = uuid.uuid4().hex[:8]

    # Log order intent — no credentials, clean params only
    logger.info(
        f"Placing {order_type} {side} order | "
        f"symbol={symbol} qty={quantity}"
        + (f" price={price}" if price else ""),
        extra={"request_id": request_id}
    )

    # Build parameter payload
    params = _build_order_params(
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        price=price
    )

    try:
        response = binance_client.place_order(params, request_id)

    except BinanceAPIError as e:
        logger.error(
            f"Order rejected by Binance | code={e.code} | {e.message}",
            extra={"request_id": request_id}
        )
        return OrderError(reason=e.message, request_id=request_id)

    except NetworkError as e:
        logger.error(
            f"Network failure placing order | {e}",
            extra={"request_id": request_id}
        )
        return OrderError(
            reason=str(e),
            request_id=request_id
        )

    except Exception as e:
        # Catch all unexpected errors — never let an unhandled exception
        # surface to the user with a raw Python traceback
        logger.error(
            f"Unexpected error placing order | {type(e).__name__}: {e}",
            extra={"request_id": request_id}
        )
        return OrderError(
            reason="An unexpected error occurred. Please check the log file for details.",
            request_id=request_id
        )

    # Parse response into structured result
    try:
        result = _parse_order_response(response, request_id)

    except (KeyError, ValueError, TypeError) as e:
        logger.error(
            f"Failed to parse order response | {e} | raw={response}",
            extra={"request_id": request_id}
        )
        return OrderError(
            reason="Order may have been placed but response could not be parsed. "
                   "Please check your open orders on Binance.",
            request_id=request_id
        )

    logger.info(
        f"Order confirmed | orderId={result.order_id} | "
        f"status={result.status} | executedQty={result.executed_qty}",
        extra={"request_id": request_id}
    )

    return result