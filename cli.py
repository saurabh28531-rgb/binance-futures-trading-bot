import typer
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from bot.cache import exchange_cache
from bot.validators import ValidationError, validate_all
from bot.orders import OrderError, OrderResult, place_order

# Single Typer app instance
app = typer.Typer(
    name="trading-bot",
    help="Binance Futures Demo Trading Bot — place MARKET and LIMIT orders from the CLI.",
    add_completion=False
)

# Rich console for all terminal output
console = Console()


def _print_order_summary(
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: Optional[float]
) -> None:
    """
    Print a formatted order request summary before placing the order.

    Args:
        symbol: Trading pair
        side: BUY or SELL
        order_type: MARKET or LIMIT
        quantity: Order quantity
        price: Limit price or None for MARKET
    """
    table = Table(
        title="Order Request Summary",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan"
    )

    table.add_column("Field", style="cyan", width=20)
    table.add_column("Value", style="white")

    table.add_row("Symbol", symbol)
    table.add_row("Side", f"[green]{side}[/green]" if side == "BUY" else f"[red]{side}[/red]")
    table.add_row("Order Type", order_type)
    table.add_row("Quantity", str(quantity))
    table.add_row("Price", str(price) if price else "Market Price")

    console.print()
    console.print(table)
    console.print()


def _print_order_result(result: OrderResult) -> None:
    """
    Print a formatted order response after successful placement.

    Args:
        result: Structured OrderResult from orders.py
    """
    table = Table(
        title="Order Response",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold green"
    )

    table.add_column("Field", style="cyan", width=20)
    table.add_column("Value", style="white")

    table.add_row("Order ID", str(result.order_id))
    table.add_row("Symbol", result.symbol)
    table.add_row(
        "Side",
        f"[green]{result.side}[/green]"
        if result.side == "BUY"
        else f"[red]{result.side}[/red]"
    )
    table.add_row("Order Type", result.order_type)
    table.add_row("Status", result.status)
    table.add_row("Quantity", str(result.quantity))
    table.add_row("Executed Qty", str(result.executed_qty))
    table.add_row(
        "Avg Price",
        str(result.avg_price) if result.avg_price else "Pending"
    )
    table.add_row(
        "Limit Price",
        str(result.price) if result.price else "N/A"
    )
    table.add_row("Request ID", result.request_id)

    console.print()
    console.print(table)
    console.print()

    console.print(
        Panel(
            f"[bold green]✅ Order placed successfully[/bold green]\n"
            f"Order ID: [bold]{result.order_id}[/bold] | "
            f"Status: [bold]{result.status}[/bold]",
            box=box.ROUNDED
        )
    )
    console.print()


def _print_error(message: str, request_id: Optional[str] = None) -> None:
    """
    Print a formatted error message.

    Args:
        message: Plain English error description
        request_id: Optional request ID for log reference
    """
    content = f"[bold red]❌ {message}[/bold red]"
    if request_id:
        content += f"\n[dim]Request ID: {request_id} — check log file for details[/dim]"

    console.print()
    console.print(Panel(content, box=box.ROUNDED))
    console.print()


@app.command()
def place_order_cmd(
    symbol: str = typer.Option(
        ...,
        "--symbol",
        "-s",
        help="Trading pair symbol. Example: BTCUSDT"
    ),
    side: str = typer.Option(
        ...,
        "--side",
        help="Order side. Must be BUY or SELL."
    ),
    order_type: str = typer.Option(
        ...,
        "--order-type",
        "-t",
        help="Order type. Must be MARKET or LIMIT."
    ),
    quantity: float = typer.Option(
        ...,
        "--quantity",
        "-q",
        help="Order quantity. Example: 0.01"
    ),
    price: Optional[float] = typer.Option(
        None,
        "--price",
        "-p",
        help="Limit price. Required for LIMIT orders only. Example: 45000.00"
    )
) -> None:
    """
    Place a MARKET or LIMIT futures order on Binance Demo Trading.

    Examples:

        MARKET BUY:
            python cli.py place-order --symbol BTCUSDT --side BUY --order-type MARKET --quantity 0.01

        LIMIT SELL:
            python cli.py place-order --symbol BTCUSDT --side SELL --order-type LIMIT --quantity 0.01 --price 45000.00
    """

    # Step 1 — Initialize exchange cache
    # Fetches exchange info once, validates symbols and filters locally
    try:
        exchange_cache.initialize()
    except SystemExit:
        _print_error(
            "Could not connect to Binance to fetch exchange info.\n"
            "   Check your internet connection and try again."
        )
        raise typer.Exit(code=1)

    # Step 2 — Validate all inputs against cache
    try:
        validated = validate_all(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price
        )
    except ValidationError as e:
        _print_error(f"Validation failed: {e}")
        raise typer.Exit(code=1)

    # Step 3 — Print order summary before placing
    _print_order_summary(
        symbol=validated["symbol"],
        side=validated["side"],
        order_type=validated["order_type"],
        quantity=validated["quantity"],
        price=validated["price"]
    )

    # Step 4 — Confirm with user before placing order
    confirmed = typer.confirm("Confirm order placement?")
    if not confirmed:
        console.print("\n[yellow]Order cancelled by user.[/yellow]\n")
        raise typer.Exit(code=0)

    # Step 5 — Place order
    console.print("\n[cyan]Placing order...[/cyan]")

    result = place_order(
        symbol=validated["symbol"],
        side=validated["side"],
        order_type=validated["order_type"],
        quantity=validated["quantity"],
        price=validated["price"]
    )

    # Step 6 — Display result
    if isinstance(result, OrderError):
        _print_error(result.reason, result.request_id)
        raise typer.Exit(code=1)

    _print_order_result(result)


def _startup_banner() -> None:
    """
    Print startup banner when app launches.
    """
    console.print(
        Panel(
            "[bold cyan]Binance Futures Demo Trading Bot[/bold cyan]\n"
            "[dim]Connected to: Binance Demo Trading Environment[/dim]\n"
            "[dim]No real funds at risk[/dim]",
            box=box.ROUNDED
        )
    )


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """
    Binance Futures Demo Trading Bot entry point.
    """
    _startup_banner()
    if ctx.invoked_subcommand is None:
        console.print(
            "[yellow]Run with --help to see available commands.[/yellow]\n"
        )


if __name__ == "__main__":
    app()