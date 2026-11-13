"""Every external input the analysis uses, in one place.

Each source is a public, keyless HTTP GET. `role` decides how the series is
used; see METHODS.md section 2 for why each competitor is in or out of the
control ("donor") pool.
"""

LLAMA = "https://api.llama.fi"

# role values:
#   treated       - NEAR Intents itself
#   donor         - clean control: does not route its flow through NEAR Intents
#   contaminated  - routes some flow through NEAR Intents; sensitivity analysis only
#   fees          - daily fees paid by users (for fee-rate comparisons)
#   revenue       - daily protocol revenue (NEAR Intents' own take)
SOURCES = [
    # --- treated -----------------------------------------------------------
    dict(id="intents_volume", role="treated", name="NEAR Intents",
         url=f"{LLAMA}/summary/dexs/near-intents?dataType=dailyVolume"),
    dict(id="intents_fees", role="fees", name="NEAR Intents",
         url=f"{LLAMA}/summary/fees/near-intents?dataType=dailyFees"),
    dict(id="intents_revenue", role="revenue", name="NEAR Intents",
         url=f"{LLAMA}/summary/fees/near-intents?dataType=dailyRevenue"),

    # --- clean donors: native cross-chain swap venues -----------------------
    dict(id="thorchain_volume", role="donor", name="THORChain",
         url=f"{LLAMA}/summary/dexs/thorchain-dex?dataType=dailyVolume"),
    dict(id="thorchain_fees", role="fees", name="THORChain",
         url=f"{LLAMA}/summary/fees/thorchain-dex?dataType=dailyFees"),
    dict(id="chainflip_volume", role="donor", name="Chainflip",
         url=f"{LLAMA}/summary/dexs/chainflip-amm?dataType=dailyVolume"),
    dict(id="chainflip_fees", role="fees", name="Chainflip",
         url=f"{LLAMA}/summary/fees/chainflip-amm?dataType=dailyFees"),
    dict(id="maya_volume", role="donor", name="Maya Protocol",
         url=f"{LLAMA}/summary/dexs/maya-protocol?dataType=dailyVolume"),
    dict(id="maya_fees", role="fees", name="Maya Protocol",
         url=f"{LLAMA}/summary/fees/maya-protocol?dataType=dailyFees"),

    # --- clean donors: bridge aggregators with no known Intents route --------
    dict(id="socket_volume", role="donor", name="SOCKET",
         url=f"{LLAMA}/summary/bridge-aggregators/socket-protocol?dataType=dailyBridgeVolume"),
    dict(id="zerox_volume", role="donor", name="0x Bridge Aggregator",
         url=f"{LLAMA}/summary/bridge-aggregators/0x-bridge-aggregator?dataType=dailyBridgeVolume"),

    # --- clean donor: the whole market --------------------------------------
    dict(id="alldex_volume", role="donor", name="All DEX volume",
         url=f"{LLAMA}/overview/dexs?excludeTotalDataChartBreakdown=true&dataType=dailyVolume"),

    # --- NEAR token price (for the issuance comparison only) ---------------
    dict(id="near_price", role="price", name="NEAR price (CoinGecko)",
         url="https://api.coingecko.com/api/v3/coins/near/market_chart?vs_currency=usd&days=365&interval=daily"),

    # --- contaminated: route part of their flow through NEAR Intents --------
    dict(id="lifi_volume", role="contaminated", name="LI.FI",
         url=f"{LLAMA}/summary/bridge-aggregators/li.fi-bridge-aggregator?dataType=dailyBridgeVolume"),
    dict(id="rango_volume", role="contaminated", name="Rango",
         url=f"{LLAMA}/summary/bridge-aggregators/rango?dataType=dailyBridgeVolume"),
    dict(id="bitget_volume", role="contaminated", name="Bitget Wallet X",
         url=f"{LLAMA}/summary/bridge-aggregators/bitget-wallet-x?dataType=dailyBridgeVolume"),
]

# Fee/volume pairs used for the fee-rate (price premium) test.
FEE_PAIRS = {
    "NEAR Intents": ("intents_fees", "intents_volume"),
    "THORChain": ("thorchain_fees", "thorchain_volume"),
    "Chainflip": ("chainflip_fees", "chainflip_volume"),
    "Maya Protocol": ("maya_fees", "maya_volume"),
}

# Native cross-chain venues: the competitor set for market share and fee rate.
COMPETITORS = ["thorchain_volume", "chainflip_volume", "maya_volume"]


def by_id(source_id):
    for s in SOURCES:
        if s["id"] == source_id:
            return s
    raise KeyError(source_id)
