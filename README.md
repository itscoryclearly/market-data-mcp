# market-data-mcp

**Live multi-exchange crypto market data as [MCP](https://modelcontextprotocol.io) tools — no API keys, no accounts.**

An [Model Context Protocol](https://modelcontextprotocol.io) server that lets any MCP-compatible AI assistant (Claude Desktop, Claude Code, etc.) pull real-time crypto prices, order books, and candles from **Coinbase** and **Kraken** — and compare a pair across both in one call. It uses only each exchange's **public, key-free** REST endpoints, so you can clone it and run it with zero setup.

```text
You:    What's BTC trading at, and is Coinbase or Kraken cheaper right now?
Agent:  (calls compare_price "BTC-USD")
        Coinbase $66,720.73 vs Kraken $66,730.50 — spread $9.77 (0.015%). Kraken is dearer; Coinbase is cheaper.
```

## Why it exists

A focused example of a well-built MCP server: tools designed around **workflows** (not raw endpoint wrappers), normalized responses across two very different exchange APIs, real error handling, and a test suite that mocks the network so it runs anywhere.

## Tools

| Tool | What it does | Example call |
| --- | --- | --- |
| `get_price` | Spot price + bid/ask + 24h volume on one exchange | `get_price("BTC-USD")` |
| `compare_price` | Same pair on Coinbase **and** Kraken, with the spread | `compare_price("ETH-USD")` |
| `get_orderbook` | Top-N bid/ask levels | `get_orderbook("BTC-USD", depth=5)` |
| `get_ohlc` | Recent OHLC candles | `get_ohlc("BTC-USD", interval="1h")` |

Symbols are flexible: `BTC-USD`, `ETH/USD`, `SOL_USDT`, or just `BTC` (quote defaults to USD). The server handles each exchange's naming quirks for you (e.g. Kraken calls Bitcoin `XBT`).

### Example output

`compare_price("BTC-USD")`:

```json
{
  "symbol": "BTC-USD",
  "coinbase": 66720.73,
  "kraken": 66730.50,
  "spread_abs": 9.77,
  "spread_pct": 0.0146,
  "cheaper": "coinbase"
}
```

`get_ohlc("BTC-USD", interval="1h", limit=2)` (newest last):

```json
[
  {"time": 1780495140, "open": 66775.79, "high": 66800.0, "low": 66762.16, "close": 66787.0, "volume": 10.48},
  {"time": 1780495200, "open": 66786.24, "high": 66834.44, "low": 66751.56, "close": 66763.74, "volume": 8.27}
]
```

## Quickstart

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/itscoryclearly/market-data-mcp
cd market-data-mcp
uv sync
```

Register it with your MCP client. For **Claude Desktop**, add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "market-data": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/market-data-mcp", "run", "market-data-mcp"]
    }
  }
}
```

Then ask your assistant something like *"compare the price of SOL on Coinbase and Kraken."*

## Development

```bash
uv sync --extra dev
uv run pytest        # tests mock the HTTP layer — no network needed
uv run ruff check .
```

## Notes

- **Public endpoints only.** No API keys, no authentication, read-only. The server never places orders or touches an account.
- **Not financial advice.** Data is provided as-is from the exchanges; availability and accuracy are theirs.
- Binance is intentionally not included.

## License

[MIT](LICENSE)
