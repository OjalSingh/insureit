"""Token prices and cost accounting, so every run reports what it cost.

Prices are USD per million tokens (Anthropic list prices, 2026-10). Cache writes cost 1.25x the
input price and cache reads 0.1x; the Message Batches API halves everything. Models that are not
listed are reported with cost `None` instead of a guess."""

PRICES = {  # model: (input, output) USD per 1M tokens
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
CACHE_WRITE = 1.25
CACHE_READ = 0.10
BATCH_DISCOUNT = 0.50

TOKEN_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens",
              "cache_read_input_tokens")


def cost_usd(model: str, usage: dict, batch: bool = False) -> float | None:
    """Cost of one or more calls to `model`, from summed usage counters."""
    price = PRICES.get(model.split(":")[-1])
    if price is None:
        return None
    inp, out = price
    total = (usage.get("input_tokens", 0) * inp
             + usage.get("cache_creation_input_tokens", 0) * inp * CACHE_WRITE
             + usage.get("cache_read_input_tokens", 0) * inp * CACHE_READ
             + usage.get("output_tokens", 0) * out) / 1_000_000
    return total * (BATCH_DISCOUNT if batch else 1.0)
