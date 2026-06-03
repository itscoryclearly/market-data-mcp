"""Async clients for Coinbase and Kraken public market-data endpoints.

Only public, key-free REST endpoints are used, so the server needs no
credentials. Every function takes an :class:`httpx.AsyncClient` rather than
creating its own, which lets the tool layer reuse one connection per request
(and lets tests inject a mock transport with zero network access).

Each exchange returns data in its own shape; these functions normalize the
pieces we care about into uniform dicts so the tools above don't have to know
that Coinbase orders candles ``[time, low, high, open, close, volume]`` while
Kraken orders them ``[time, open, high, low, close, vwap, volume, count]``.
"""

from __future__ import annotations

from typing import Any

import httpx

from .symbols import Symbol

COINBASE_BASE = "https://api.exchange.coinbase.com"
KRAKEN_BASE = "https://api.kraken.com/0/public"

TIMEOUT = httpx.Timeout(10.0)
_HEADERS = {"User-Agent": "market-data-mcp"}

# Friendly interval -> (Coinbase granularity in seconds, Kraken interval in minutes).
# Only intervals supported by *both* exchanges are offered, so behaviour is
# consistent no matter which exchange the caller picks.
INTERVALS: dict[str, tuple[int, int]] = {
    "1m": (60, 1),
    "5m": (300, 5),
    "15m": (900, 15),
    "1h": (3600, 60),
    "1d": (86400, 1440),
}


class MarketDataError(Exception):
    """Base class for errors surfaced to the agent as tool failures."""


class UnknownSymbolError(MarketDataError):
    """The exchange does not list the requested trading pair."""


class ExchangeError(MarketDataError):
    """The exchange was reachable but returned an error or unexpected payload."""


async def _get(
    client: httpx.AsyncClient, url: str, params: dict[str, Any] | None = None
) -> httpx.Response:
    try:
        return await client.get(url, params=params, headers=_HEADERS, timeout=TIMEOUT)
    except httpx.HTTPError as exc:  # network/timeout/DNS -> actionable message
        raise ExchangeError(f"Could not reach {url}: {exc}") from exc


# --------------------------------------------------------------------------- #
# Coinbase (api.exchange.coinbase.com)
# --------------------------------------------------------------------------- #
async def _coinbase_json(
    client: httpx.AsyncClient, path: str, params: dict[str, Any] | None = None
) -> Any:
    resp = await _get(client, f"{COINBASE_BASE}{path}", params)
    if resp.status_code == 404:
        raise UnknownSymbolError(
            "Coinbase does not list that pair. Check the symbol, e.g. 'BTC-USD', 'ETH-USD'."
        )
    if resp.status_code >= 400:
        raise ExchangeError(f"Coinbase returned HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()


async def coinbase_ticker(client: httpx.AsyncClient, sym: Symbol) -> dict[str, Any]:
    data = await _coinbase_json(client, f"/products/{sym.coinbase}/ticker")
    return {
        "exchange": "coinbase",
        "symbol": str(sym),
        "price": float(data["price"]),
        "bid": float(data["bid"]),
        "ask": float(data["ask"]),
        "volume_24h": float(data["volume"]),
        "time": data.get("time"),
    }


async def coinbase_book(client: httpx.AsyncClient, sym: Symbol, depth: int) -> dict[str, Any]:
    level = 2 if depth > 1 else 1
    data = await _coinbase_json(client, f"/products/{sym.coinbase}/book", {"level": level})
    return {
        "exchange": "coinbase",
        "symbol": str(sym),
        "bids": [[float(price), float(size)] for price, size, *_ in data["bids"][:depth]],
        "asks": [[float(price), float(size)] for price, size, *_ in data["asks"][:depth]],
        "time": data.get("time"),
    }


async def coinbase_candles(
    client: httpx.AsyncClient, sym: Symbol, granularity: int, limit: int
) -> list[dict[str, Any]]:
    # Coinbase returns newest-first: [time, low, high, open, close, volume].
    data = await _coinbase_json(
        client, f"/products/{sym.coinbase}/candles", {"granularity": granularity}
    )
    candles = []
    for time_, low, high, open_, close, volume in data[:limit]:
        candles.append(
            {
                "time": int(time_),
                "open": float(open_),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": float(volume),
            }
        )
    return candles


# --------------------------------------------------------------------------- #
# Kraken (api.kraken.com/0/public)
# --------------------------------------------------------------------------- #
def _kraken_payload(data: dict[str, Any]) -> Any:
    """Extract the pair payload from a Kraken envelope.

    Kraken wraps results as ``{"error": [...], "result": {...}}``. The result is
    keyed by Kraken's *normalized* pair name (e.g. ``XXBTZUSD``), not the name we
    sent, and some endpoints (OHLC) tuck a ``"last"`` cursor alongside it -- so we
    return the first non-``last`` value rather than guessing the key.
    """
    if data.get("error"):
        message = "; ".join(data["error"])
        if "Unknown asset pair" in message:
            raise UnknownSymbolError(
                "Kraken does not list that pair. Check the symbol, e.g. 'BTC-USD', 'ETH-USD'."
            )
        raise ExchangeError(f"Kraken error: {message}")
    for key, value in data.get("result", {}).items():
        if key != "last":
            return value
    raise ExchangeError("Kraken returned an empty result.")


async def _kraken_json(client: httpx.AsyncClient, path: str, params: dict[str, Any]) -> Any:
    resp = await _get(client, f"{KRAKEN_BASE}{path}", params)
    if resp.status_code >= 400:
        raise ExchangeError(f"Kraken returned HTTP {resp.status_code}: {resp.text[:200]}")
    return _kraken_payload(resp.json())


async def kraken_ticker(client: httpx.AsyncClient, sym: Symbol) -> dict[str, Any]:
    # Ticker fields: a=ask, b=bid, c=[last_price, lot_vol], v=[today, last24h] volume.
    t = await _kraken_json(client, "/Ticker", {"pair": sym.kraken})
    return {
        "exchange": "kraken",
        "symbol": str(sym),
        "price": float(t["c"][0]),
        "bid": float(t["b"][0]),
        "ask": float(t["a"][0]),
        "volume_24h": float(t["v"][1]),
        "time": None,  # Kraken's ticker carries no timestamp.
    }


async def kraken_depth(client: httpx.AsyncClient, sym: Symbol, depth: int) -> dict[str, Any]:
    book = await _kraken_json(client, "/Depth", {"pair": sym.kraken, "count": depth})
    return {
        "exchange": "kraken",
        "symbol": str(sym),
        "bids": [[float(price), float(vol)] for price, vol, *_ in book["bids"][:depth]],
        "asks": [[float(price), float(vol)] for price, vol, *_ in book["asks"][:depth]],
        "time": None,
    }


async def kraken_ohlc(
    client: httpx.AsyncClient, sym: Symbol, interval_minutes: int, limit: int
) -> list[dict[str, Any]]:
    # Kraken returns oldest-first: [time, open, high, low, close, vwap, volume, count].
    series = await _kraken_json(client, "/OHLC", {"pair": sym.kraken, "interval": interval_minutes})
    candles = []
    for time_, open_, high, low, close, _vwap, volume, _count in series[-limit:]:
        candles.append(
            {
                "time": int(time_),
                "open": float(open_),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": float(volume),
            }
        )
    return candles
