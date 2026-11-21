"""List prices for the models this agent calls, so the trace shows what a call would cost on the paid tier.

USD per 1M tokens, Gemini API standard tier, checked 2026-11-20 at aistudio.google.com/docs/pricing.
Output prices include thinking tokens. Both models are free on the free tier, which this demo uses,
so these numbers are the cost at scale, not a bill. Gemini 3.8 Flash prices double on 2027-01-01.
"""

from types import MappingProxyType

from app.agent.llm import Usage

TOKENS_PER_PRICE_UNIT = 1_000_000

# model -> (input, output)
PRICES_USD_PER_M = MappingProxyType({
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.5-flash-lite": (0.30, 2.50),
})


def cost_usd(usage: Usage) -> float:
    """Unknown models cost 0 rather than a guess; add the model above when it changes."""
    price_in, price_out = PRICES_USD_PER_M.get(usage.model, (0.0, 0.0))
    return (usage.tokens_in * price_in + usage.tokens_out * price_out) / TOKENS_PER_PRICE_UNIT
