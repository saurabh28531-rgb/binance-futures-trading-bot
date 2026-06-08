import math
from typing import Optional

from bot.cache import exchange_cache


class ValidationError(Exception):
    """
    Raised when user input fails validation.

    Separate from API errors — this is caught before any API call is made.
    Carries a user-friendly message that is displayed directly in the terminal.
    """
    pass


def validate_symbol(symbol: str) -> str:
    """
    Validate trading symbol against local exchange cache.

    Rules:
        - Must not be empty
        - Must exist in Binance Futures as an active perpetual contract

    Args:
        symbol: Trading pair symbol provided by user

    Returns:
        Cleaned uppercase symbol string

    Raises:
        ValidationError: If symbol is invalid or not found
    """
    if not symbol or not symbol.strip():
        raise ValidationError(
            "Symbol cannot be empty. Example: BTCUSDT"
        )

    cleaned = symbol.strip().upper()

    if not exchange_cache.is_valid_symbol(cleaned):
        # Give user a helpful hint — show some valid symbols
        sample = ", ".join(exchange_cache.get_all_symbols()[:5])
        raise ValidationError(
            f"'{cleaned}' is not a valid Binance Futures perpetual symbol.\n"
            f"   Valid examples: {sample}, ..."
        )

    return cleaned


def validate_side(side: str) -> str:
    """
    Validate order side.

    Rules:
        - Must be BUY or SELL (case insensitive)

    Args:
        side: Order side provided by user

    Returns:
        Uppercase side string: 'BUY' or 'SELL'

    Raises:
        ValidationError: If side is not BUY or SELL
    """
    if not side or not side.strip():
        raise ValidationError(
            "Side cannot be empty. Must be BUY or SELL."
        )

    cleaned = side.strip().upper()

    if cleaned not in ("BUY", "SELL"):
        raise ValidationError(
            f"Invalid side '{cleaned}'. Must be BUY or SELL."
        )

    return cleaned


def validate_order_type(order_type: str) -> str:
    """
    Validate order type.

    Rules:
        - Must be MARKET or LIMIT (case insensitive)

    Args:
        order_type: Order type provided by user

    Returns:
        Uppercase order type string: 'MARKET' or 'LIMIT'

    Raises:
        ValidationError: If order type is not MARKET or LIMIT
    """
    if not order_type or not order_type.strip():
        raise ValidationError(
            "Order type cannot be empty. Must be MARKET or LIMIT."
        )

    cleaned = order_type.strip().upper()

    if cleaned not in ("MARKET", "LIMIT"):
        raise ValidationError(
            f"Invalid order type '{cleaned}'. Must be MARKET or LIMIT."
        )

    return cleaned


def validate_quantity(quantity: float, symbol: str) -> float:
    """
    Validate order quantity against local LOT_SIZE rules.

    Rules:
        - Must be a positive finite number
        - Must meet symbol's minimum quantity
        - Must not exceed symbol's maximum quantity
        - Must conform to symbol's step size precision

    Args:
        quantity: Order quantity provided by user
        symbol: Already validated uppercase symbol string

    Returns:
        Validated quantity as float

    Raises:
        ValidationError: If quantity violates any rule
    """
    if quantity is None:
        raise ValidationError("Quantity cannot be empty.")

    if not isinstance(quantity, (int, float)):
        raise ValidationError(
            f"Invalid quantity '{quantity}'. Must be a number. Example: 0.01"
        )

    if math.isinf(quantity) or math.isnan(quantity):
        raise ValidationError(
            f"Invalid quantity '{quantity}'. Must be a finite number."
        )

    if quantity <= 0:
        raise ValidationError(
            f"Invalid quantity '{quantity}'. Quantity must be greater than zero."
        )

    # Validate against LOT_SIZE rules from cache — zero API cost
    lot_size = exchange_cache.get_lot_size(symbol)
    if lot_size:
        min_qty = lot_size["min_qty"]
        max_qty = lot_size["max_qty"]
        step_size = lot_size["step_size"]

        if quantity < min_qty:
            raise ValidationError(
                f"Quantity {quantity} is below the minimum allowed for {symbol}.\n"
                f"   Minimum quantity: {min_qty}"
            )

        if quantity > max_qty:
            raise ValidationError(
                f"Quantity {quantity} exceeds the maximum allowed for {symbol}.\n"
                f"   Maximum quantity: {max_qty}"
            )

        # Check step size precision
        # e.g. step_size=0.001 means 0.0015 is invalid, 0.001 or 0.002 is valid
        if step_size > 0:
            remainder = round(quantity % step_size, 10)
            if remainder != 0 and round(remainder - step_size, 10) != 0:
                raise ValidationError(
                    f"Quantity {quantity} does not conform to step size for {symbol}.\n"
                    f"   Step size: {step_size} — Example valid quantity: {min_qty}"
                )

    return float(quantity)


def validate_price(
    price: Optional[float],
    order_type: str,
    symbol: str
) -> Optional[float]:
    """
    Validate order price against local PRICE_FILTER rules.

    Rules:
        - Must not be provided for MARKET orders
        - Required for LIMIT orders
        - Must meet symbol's minimum price
        - Must not exceed symbol's maximum price
        - Must conform to symbol's tick size precision

    Args:
        price: Order price provided by user
        order_type: Already validated order type string
        symbol: Already validated uppercase symbol string

    Returns:
        Validated price as float or None for MARKET orders

    Raises:
        ValidationError: If price rules are violated
    """
    if order_type == "MARKET":
        if price is not None:
            raise ValidationError(
                "Price must not be provided for MARKET orders.\n"
                "   MARKET orders execute at current market price."
            )
        return None

    if order_type == "LIMIT":
        if price is None:
            raise ValidationError(
                "Price is required for LIMIT orders.\n"
                "   Example: --price 45000.00"
            )

        if not isinstance(price, (int, float)):
            raise ValidationError(
                f"Invalid price '{price}'. Must be a number. Example: 45000.00"
            )

        if math.isinf(price) or math.isnan(price):
            raise ValidationError(
                f"Invalid price '{price}'. Must be a finite number."
            )

        if price <= 0:
            raise ValidationError(
                f"Invalid price '{price}'. Price must be greater than zero."
            )

        # Validate against PRICE_FILTER rules from cache — zero API cost
        price_filter = exchange_cache.get_price_filter(symbol)
        if price_filter:
            min_price = price_filter["min_price"]
            max_price = price_filter["max_price"]
            tick_size = price_filter["tick_size"]

            if min_price > 0 and price < min_price:
                raise ValidationError(
                    f"Price {price} is below the minimum allowed for {symbol}.\n"
                    f"   Minimum price: {min_price}"
                )

            if max_price > 0 and price > max_price:
                raise ValidationError(
                    f"Price {price} exceeds the maximum allowed for {symbol}.\n"
                    f"   Maximum price: {max_price}"
                )

            # Check tick size precision
            if tick_size > 0:
                remainder = round(price % tick_size, 10)
                if remainder != 0 and round(remainder - tick_size, 10) != 0:
                    raise ValidationError(
                        f"Price {price} does not conform to tick size for {symbol}.\n"
                        f"   Tick size: {tick_size}"
                    )

        return float(price)


def validate_all(
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: Optional[float] = None
) -> dict:
    """
    Run all validations in sequence and return cleaned validated parameters.

    Single entry point for all validation — called by cli.py before
    any order is placed. Validates in the correct order since some
    validators depend on previously validated values.

    Args:
        symbol: Trading pair symbol
        side: Order side BUY or SELL
        order_type: MARKET or LIMIT
        quantity: Order quantity
        price: Order price, required for LIMIT only

    Returns:
        Dictionary of validated and cleaned parameters ready for API call

    Raises:
        ValidationError: If any input fails validation
    """
    # Order matters here:
    # 1. order_type must be validated before price (price depends on order_type)
    # 2. symbol must be validated before quantity (quantity depends on symbol)
    validated_symbol = validate_symbol(symbol)
    validated_order_type = validate_order_type(order_type)

    return {
        "symbol": validated_symbol,
        "side": validate_side(side),
        "order_type": validated_order_type,
        "quantity": validate_quantity(quantity, validated_symbol),
        "price": validate_price(price, validated_order_type, validated_symbol)
    }