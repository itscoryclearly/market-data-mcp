"""Symbol parsing and per-exchange formatting.

Users speak in human-friendly pairs like ``BTC-USD``, ``ETH/USD``, or a bare
``BTC`` (quote defaults to USD). Each exchange names the same pair differently
-- Coinbase wants ``BTC-USD`` while Kraken wants ``XBTUSD`` -- so we parse once
into a :class:`Symbol` and render the exchange-specific form on demand. Keeping
this in one place means the tool layer never hard-codes an exchange's quirks.
"""

from __future__ import annotations

from dataclasses import dataclass

# Kraken still uses a few legacy asset codes (most notably XBT for Bitcoin).
# Its public API accepts these "altname" pairs (e.g. XBTUSD, ETHUSD) directly.
_KRAKEN_BASE_ALIASES = {"BTC": "XBT"}

# Separators we accept between base and quote, in priority order.
_SEPARATORS = ("-", "/", "_")


@dataclass(frozen=True)
class Symbol:
    """A parsed trading pair, e.g. ``Symbol("BTC", "USD")``."""

    base: str
    quote: str

    @property
    def coinbase(self) -> str:
        """Coinbase product id, e.g. ``BTC-USD``."""
        return f"{self.base}-{self.quote}"

    @property
    def kraken(self) -> str:
        """Kraken pair altname, e.g. ``XBTUSD`` (BTC is renamed to XBT)."""
        base = _KRAKEN_BASE_ALIASES.get(self.base, self.base)
        return f"{base}{self.quote}"

    def __str__(self) -> str:
        return f"{self.base}-{self.quote}"


def parse_symbol(raw: str, default_quote: str = "USD") -> Symbol:
    """Parse a user-supplied symbol into a :class:`Symbol`.

    Accepts ``BTC-USD``, ``ETH/USD``, ``SOL_USDT`` or a bare base like ``BTC``
    (which uses ``default_quote``). Case-insensitive.

    Raises:
        ValueError: if the input is empty or only partially specifies a pair
            (e.g. ``"BTC-"``). The message suggests the correct format so an
            agent can self-correct.
    """
    if not raw or not raw.strip():
        raise ValueError("Symbol is empty. Provide a pair like 'BTC-USD' or just 'BTC'.")

    text = raw.strip().upper()
    for sep in _SEPARATORS:
        if sep in text:
            base, _, quote = text.partition(sep)
            base, quote = base.strip(), quote.strip()
            if not base or not quote:
                raise ValueError(f"Could not parse symbol {raw!r}. Use BASE-QUOTE, e.g. 'BTC-USD'.")
            return Symbol(base, quote)

    # No separator -> treat the whole token as the base and default the quote.
    return Symbol(text, default_quote)
