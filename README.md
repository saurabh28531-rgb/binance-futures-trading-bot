# Binance Futures Demo Trading Bot

A Python CLI trading bot for Binance Futures Demo Trading (USDT-M). Places MARKET and LIMIT orders with structured logging, full input validation, and clean separation of concerns.

---

## Table of Contents

- [Project Structure](#project-structure)
- [Setup](#setup)
- [How to Run](#how-to-run)
- [CLI Arguments](#cli-arguments)
- [Validation](#validation)
- [Logging](#logging)
- [Error Handling](#error-handling)
- [Security](#security)
- [Configuration](#configuration)
- [Assumptions](#assumptions)
- [Dependencies](#dependencies)

---

## Project Structure

```
TradingBot/
├── bot/
│   ├── __init__.py
│   ├── cache.py             # Exchange info cache with 24hr TTL
│   ├── client.py            # Binance API client — HMAC-SHA256 signing, retry logic
│   ├── config.py            # Environment variable loading and validation
│   ├── logging_config.py    # Structured file and console logging
│   ├── orders.py            # Order placement logic
│   └── validators.py        # Input validation against local cache
├── cli.py                   # CLI entry point
├── .env.example             # Environment variable template
├── requirements.txt         # Pinned dependencies
└── logs/                    # Auto-generated log files (gitignored)
```

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/trading-bot.git
cd trading-bot
```

### 2. Create and activate virtual environment

```bash
python -m venv venv
```

Windows:
```bash
venv\Scripts\activate
```

macOS / Linux:
```bash
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your credentials:

```env
BINANCE_API_KEY=your_api_key_here
BINANCE_SECRET_KEY=your_secret_key_here
BINANCE_BASE_URL=https://demo-fapi.binance.com
```

**How to get API credentials:**
1. Go to `https://demo.binance.com`
2. Log in with your Binance account
3. Click your profile icon → Demo Trading API
4. Click Create API → System Generated
5. Enable Futures permission
6. Copy both API Key and Secret Key immediately — Secret is shown only once

---

## How to Run

### View all available commands

```bash
python cli.py --help
```

### Place a MARKET BUY order

```bash
python cli.py place-order-cmd --symbol BTCUSDT --side BUY --order-type MARKET --quantity 0.001
```

### Place a LIMIT SELL order

```bash
python cli.py place-order-cmd --symbol BTCUSDT --side SELL --order-type LIMIT --quantity 0.001 --price 150000.00
```

### View command-level help

```bash
python cli.py place-order-cmd --help
```

---

## CLI Arguments

| Argument | Required | Description | Example |
|---|---|---|---|
| `--symbol` | Yes | Trading pair symbol | `BTCUSDT` |
| `--side` | Yes | Order side | `BUY` or `SELL` |
| `--order-type` | Yes | Order type | `MARKET` or `LIMIT` |
| `--quantity` | Yes | Order quantity | `0.001` |
| `--price` | LIMIT only | Limit price | `45000.00` |

---

## Validation

All inputs are validated locally before any API call is made. Exchange structural
rules are fetched once at startup and cached with a 24-hour TTL — zero unnecessary API calls.

| Validation | How | API Cost |
|---|---|---|
| Symbol exists on Binance Futures | Local cache lookup | Zero |
| Side is BUY or SELL | Local check | Zero |
| Order type is MARKET or LIMIT | Local check | Zero |
| Quantity meets min / max / step size | Local cache lookup | Zero |
| Price meets min / max / tick size | Local cache lookup | Zero |
| Price not provided for MARKET orders | Local check | Zero |
| Price required for LIMIT orders | Local check | Zero |

---

## Logging

Log files are written to `logs/trading_bot_YYYYMMDD.log` and rotate at 5MB (last 3 files kept).

**Log line format:**
```
TIMESTAMP | LEVEL    | MODULE     | [REQUEST_ID] | MESSAGE
```

**Example output:**
```
2026-06-08 14:19:51 | INFO     | bot.cache   | [-]        | Exchange cache ready — 566 active perpetual symbols loaded
2026-06-08 14:19:56 | INFO     | bot.orders  | [4ce78753] | Placing MARKET BUY order | symbol=BTCUSDT qty=0.001
2026-06-08 14:19:56 | INFO     | bot.orders  | [4ce78753] | Order confirmed | orderId=14487640266 | status=NEW
```

- File handler receives DEBUG and above — full detail for debugging
- Console handler receives INFO and above — clean output for users
- Credentials never appear in any log line
- Every order carries a unique Request ID for end-to-end traceability

---

## Error Handling

Three independent layers catch errors before they reach the user as raw Python tracebacks.

**Layer 1 — Typer** catches wrong data types before any code runs:
```
Error: Invalid value for '--quantity': 'abc' is not a valid float.
```

**Layer 2 — Validators** catch wrong values locally at zero API cost:
```
❌ Validation failed: 'QWEERT' is not a valid Binance Futures symbol.
❌ Validation failed: Price is required for LIMIT orders.
```

**Layer 3 — API error translator** maps Binance error codes to plain English:
```
❌ Insufficient balance to place this order.
❌ Invalid signature. Check your API secret key.
```

---

## Security

| Practice | Implementation |
|---|---|
| Credentials never in source code | Loaded from `.env` via `python-dotenv` |
| `.env` excluded from Git | Enforced via `.gitignore` |
| API key never in URLs | Sent in `X-MBX-APIKEY` request header only |
| Secret key never logged | Used only inside HMAC-SHA256 signing function |
| Config immutable after startup | `frozen=True` dataclass prevents accidental mutation |
| Requests never hang | Explicit connect, read, write, pool timeouts on every call |
| Transient failures retried safely | Exponential backoff — 1s, 2s, 4s between attempts |

---

## Configuration

Optional variables with sensible defaults — only change if needed:

| Variable | Default | Description |
|---|---|---|
| `REQUEST_TIMEOUT_CONNECT` | `5.0` | Seconds to wait to establish connection |
| `REQUEST_TIMEOUT_READ` | `10.0` | Seconds to wait for API response |
| `MAX_RETRIES` | `3` | Retry attempts on transient failures |
| `LOG_LEVEL` | `INFO` | Console log level (`DEBUG`, `INFO`, `WARNING`) |

---

## Assumptions

- Binance Demo Trading environment is used throughout — no real funds at risk
- Base URL `https://demo-fapi.binance.com` is the correct endpoint for Demo Futures API
- Only USDT-M perpetual contracts are supported
- LIMIT orders use `timeInForce=GTC` (Good Till Cancelled) by default
- Exchange structural rules (LOT_SIZE, PRICE_FILTER) are stable enough for a 24-hour cache TTL
- Python 3.10 or higher is required

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `httpx` | 0.27.0 | HTTP client for Binance API calls |
| `typer` | 0.9.0 | CLI framework |
| `click` | 8.1.7 | CLI dependency (pinned for compatibility) |
| `rich` | 13.7.1 | Terminal output formatting |
| `python-dotenv` | 1.0.1 | Environment variable loading from `.env` |
