"""market-data-mcp -- crypto market data from Coinbase and Kraken as MCP tools.

Exposes four read-only tools over public, key-free exchange endpoints:
``get_price``, ``compare_price``, ``get_orderbook`` and ``get_ohlc``. The tools
are thin orchestration over :mod:`market_data_mcp.exchanges`; symbol quirks and
response shapes are normalized there so each tool reads as a clean workflow.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from . import exchanges as ex
from .symbols import parse_symbol

mcp = FastMCP("market-data-mcp")

_EXCHANGES = ("coinbase", "kraken")


def _require_exchange(exchange: str) -> str:
    normalized = exchange.lower().strip()
    if normalized not in _EXCHANGES:
        raise ValueError(f"Unknown exchange {exchange!r}. Choose 'coinbase' or 'kraken'.")
    return normalized


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=ex.TIMEOUT)


@mcp.tool()
async def get_price(symbol: str, exchange: str = "coinbase") -> dict[str, Any]:
    """Get the current spot price (with bid, ask and 24h volume) for a crypto pair.

    Args:
        symbol: A pair like "BTC-USD" or "ETH/USD", or a bare base like "BTC"
            (the quote defaults to USD).
        exchange: "coinbase" (default) or "kraken".

    Returns:
        {exchange, symbol, price, bid, ask, volume_24h, time}. ``time`` is null
        for Kraken, whose ticker carries no timestamp.

    Read-only; uses only public endpoints (no API key). For a cross-exchange
    view use ``compare_price`` instead of calling this twice.
    """
    sym = parse_symbol(symbol)
    venue = _require_exchange(exchange)
    async with _client() as client:
        if venue == "coinbase":
            return await ex.coinbase_ticker(client, sym)
        return await ex.kraken_ticker(client, sym)


@mcp.tool()
async def compare_price(symbol: str) -> dict[str, Any]:
    """Compare a pair's spot price on Coinbase vs Kraken and report the spread.

    Fetches both exchanges concurrently -- handy for spotting cross-exchange
    dislocations or sanity-checking a quote.

    Args:
        symbol: A pair like "BTC-USD", "ETH/USD", or a bare base like "BTC".

    Returns:
        {symbol, coinbase, kraken, spread_abs, spread_pct, cheaper} where
        ``cheaper`` is "coinbase", "kraken" or "equal". Read-only, public data.
    """
    sym = parse_symbol(symbol)
    async with _client() as client:
        coinbase, kraken = await asyncio.gather(
            ex.coinbase_ticker(client, sym),
            ex.kraken_ticker(client, sym),
        )

    cb_price, kr_price = coinbase["price"], kraken["price"]
    spread = abs(cb_price - kr_price)
    mid = (cb_price + kr_price) / 2
    if cb_price < kr_price:
        cheaper = "coinbase"
    elif kr_price < cb_price:
        cheaper = "kraken"
    else:
        cheaper = "equal"

    return {
        "symbol": str(sym),
        "coinbase": cb_price,
        "kraken": kr_price,
        "spread_abs": round(spread, 8),
        "spread_pct": round(spread / mid * 100, 4) if mid else None,
        "cheaper": cheaper,
    }


@mcp.tool()
async def get_orderbook(symbol: str, exchange: str = "coinbase", depth: int = 5) -> dict[str, Any]:
    """Get the top bid/ask levels of the order book for a pair.

    Args:
        symbol: A pair like "BTC-USD" or a bare base like "BTC".
        exchange: "coinbase" (default) or "kraken".
        depth: Number of levels per side, clamped to 1-50.

    Returns:
        {exchange, symbol, bids, asks, time} where bids/asks are
        ``[[price, size], ...]`` sorted best-first. Read-only, public data.
    """
    sym = parse_symbol(symbol)
    venue = _require_exchange(exchange)
    depth = max(1, min(depth, 50))
    async with _client() as client:
        if venue == "coinbase":
            return await ex.coinbase_book(client, sym, depth)
        return await ex.kraken_depth(client, sym, depth)


@mcp.tool()
async def get_ohlc(
    symbol: str, interval: str = "1h", exchange: str = "coinbase", limit: int = 20
) -> list[dict[str, Any]]:
    """Get recent OHLC candles for a pair.

    Args:
        symbol: A pair like "BTC-USD" or a bare base like "BTC".
        interval: One of "1m", "5m", "15m", "1h", "1d" (supported on both
            exchanges).
        exchange: "coinbase" (default) or "kraken".
        limit: Number of most-recent candles to return, clamped to 1-100.

    Returns:
        A newest-last list of {time, open, high, low, close, volume}. ``time`` is
        a Unix timestamp (seconds). Read-only, public data.
    """
    sym = parse_symbol(symbol)
    venue = _require_exchange(exchange)
    if interval not in ex.INTERVALS:
        raise ValueError(
            f"Unknown interval {interval!r}. Choose one of: {', '.join(ex.INTERVALS)}."
        )
    coinbase_granularity, kraken_minutes = ex.INTERVALS[interval]
    limit = max(1, min(limit, 100))
    async with _client() as client:
        if venue == "coinbase":
            candles = await ex.coinbase_candles(client, sym, coinbase_granularity, limit)
            candles.reverse()  # Coinbase is newest-first; return newest-last for consistency.
            return candles
        return await ex.kraken_ohlc(client, sym, kraken_minutes, limit)


def main() -> None:
    """Console-script entry point: run the server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
