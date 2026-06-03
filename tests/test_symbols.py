import pytest

from market_data_mcp.symbols import Symbol, parse_symbol


@pytest.mark.parametrize(
    ("raw", "base", "quote"),
    [
        ("BTC-USD", "BTC", "USD"),
        ("eth/usd", "ETH", "USD"),
        ("SOL_USDT", "SOL", "USDT"),
        ("  doge-usd  ", "DOGE", "USD"),
        ("BTC", "BTC", "USD"),  # bare base defaults quote to USD
    ],
)
def test_parse_symbol_variants(raw, base, quote):
    sym = parse_symbol(raw)
    assert sym == Symbol(base, quote)


def test_exchange_formatting_and_btc_alias():
    sym = parse_symbol("BTC-USD")
    assert sym.coinbase == "BTC-USD"
    assert sym.kraken == "XBTUSD"  # Kraken renames BTC -> XBT
    assert str(sym) == "BTC-USD"


@pytest.mark.parametrize("bad", ["", "   ", "BTC-", "/USD"])
def test_parse_symbol_rejects_malformed(bad):
    with pytest.raises(ValueError):
        parse_symbol(bad)
