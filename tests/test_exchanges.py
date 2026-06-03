"""Exchange-client tests with a mocked HTTP layer (no network).

We drive the real client functions through :class:`httpx.MockTransport`, feeding
them canned payloads shaped exactly like the live Coinbase/Kraken responses. The
canned shapes double as documentation of what each endpoint actually returns.
"""

import httpx
import pytest

from market_data_mcp import exchanges as ex
from market_data_mcp.exchanges import ExchangeError, UnknownSymbolError
from market_data_mcp.symbols import parse_symbol

BTC = parse_symbol("BTC-USD")


def client_for(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# --------------------------------------------------------------------------- #
# Coinbase
# --------------------------------------------------------------------------- #
async def test_coinbase_ticker_parses_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/products/BTC-USD/ticker"
        return httpx.Response(
            200,
            json={
                "ask": "101.0",
                "bid": "99.0",
                "volume": "123.4",
                "price": "100.0",
                "time": "2026-01-01T00:00:00Z",
            },
        )

    async with client_for(handler) as client:
        result = await ex.coinbase_ticker(client, BTC)

    assert result == {
        "exchange": "coinbase",
        "symbol": "BTC-USD",
        "price": 100.0,
        "bid": 99.0,
        "ask": 101.0,
        "volume_24h": 123.4,
        "time": "2026-01-01T00:00:00Z",
    }


async def test_coinbase_candles_reorders_to_ohlcv():
    # Coinbase candle order is [time, low, high, open, close, volume].
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[[1700000000, 90.0, 110.0, 95.0, 105.0, 12.5]])

    async with client_for(handler) as client:
        candles = await ex.coinbase_candles(client, BTC, granularity=3600, limit=10)

    assert candles == [
        {
            "time": 1700000000,
            "open": 95.0,
            "high": 110.0,
            "low": 90.0,
            "close": 105.0,
            "volume": 12.5,
        }
    ]


async def test_coinbase_unknown_symbol_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "NotFound"})

    async with client_for(handler) as client:
        with pytest.raises(UnknownSymbolError):
            await ex.coinbase_ticker(client, parse_symbol("NOPE-USD"))


# --------------------------------------------------------------------------- #
# Kraken
# --------------------------------------------------------------------------- #
async def test_kraken_ticker_unwraps_normalized_pair_key():
    # Result is keyed by Kraken's own name (XXBTZUSD), not what we sent.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "error": [],
                "result": {
                    "XXBTZUSD": {
                        "a": ["101.0", "1", "1.0"],
                        "b": ["99.0", "1", "1.0"],
                        "c": ["100.0", "0.1"],
                        "v": ["10.0", "123.4"],
                    }
                },
            },
        )

    async with client_for(handler) as client:
        result = await ex.kraken_ticker(client, BTC)

    assert result["price"] == 100.0
    assert result["bid"] == 99.0
    assert result["ask"] == 101.0
    assert result["volume_24h"] == 123.4  # second element = trailing 24h


async def test_kraken_ohlc_ignores_last_cursor_key():
    # OHLC result holds the series under the pair key AND a sibling "last" int.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "error": [],
                "result": {
                    "XXBTZUSD": [
                        [1700000000, "95.0", "110.0", "90.0", "105.0", "100.0", "12.5", 7]
                    ],
                    "last": 1700000000,
                },
            },
        )

    async with client_for(handler) as client:
        candles = await ex.kraken_ohlc(client, BTC, interval_minutes=60, limit=10)

    assert candles == [
        {
            "time": 1700000000,
            "open": 95.0,
            "high": 110.0,
            "low": 90.0,
            "close": 105.0,
            "volume": 12.5,
        }
    ]


async def test_kraken_unknown_symbol_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": ["EQuery:Unknown asset pair"], "result": {}})

    async with client_for(handler) as client:
        with pytest.raises(UnknownSymbolError):
            await ex.kraken_ticker(client, parse_symbol("NOPE-USD"))


async def test_kraken_generic_error_raises_exchange_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": ["EGeneral:Invalid arguments"], "result": {}})

    async with client_for(handler) as client:
        with pytest.raises(ExchangeError):
            await ex.kraken_ticker(client, BTC)
