"""The instrument universe Wolfee tracks.

Moved verbatim from ``analysis.py`` (which re-exports these names) so the
symbol lists can be used without importing pandas. Symbols are in provider
(Yahoo Finance) form: BIST tickers carry the ``.IS`` suffix.
"""

# ============================================================
# BIST STOCKS — Expanded coverage (~150 stocks)
# ============================================================
BIST_SYMBOLS = [
    # Major Banks (10)
    "AKBNK.IS", "GARAN.IS", "HALKB.IS", "ISCTR.IS", "YKBNK.IS",
    "VAKBN.IS", "TSKB.IS", "SKBNK.IS", "ALBRK.IS", "ICBCT.IS",

    # Major Holdings & Investment (15)
    "KCHOL.IS", "SAHOL.IS", "DOHOL.IS", "EKGYO.IS", "GSDHO.IS",
    "BIMAS.IS", "SISE.IS", "EREGL.IS", "ARCLK.IS", "ENKAI.IS",
    "AGHOL.IS", "GLYHO.IS", "ISGYO.IS", "AKSGY.IS", "HLGYO.IS",

    # Energy & Utilities (12)
    "EUPWR.IS", "SMRTG.IS", "ODAS.IS", "ASTOR.IS", "AYDEM.IS",
    "ZOREN.IS", "KONTR.IS", "GWIND.IS", "AKSEN.IS", "AYEN.IS",
    "AKSA.IS", "ENJSA.IS",

    # Industry & Auto (15)
    "FROTO.IS", "TOASO.IS", "TTRAK.IS", "TMSN.IS", "KARSN.IS",
    "PETKM.IS", "TUPRS.IS", "VESTL.IS", "VESBE.IS", "DOAS.IS",
    "OTKAR.IS", "EGEEN.IS", "BRISA.IS", "FMIZP.IS", "GUBRF.IS",

    # Aviation & Transport (6)
    "THYAO.IS", "PGSUS.IS", "TAVHL.IS", "CLEBI.IS", "BEYAZ.IS", "RYSAS.IS",

    # Retail & Food (10)
    "MGROS.IS", "SOKM.IS", "AEFES.IS", "CCOLA.IS", "ULKER.IS",
    "MAVI.IS", "BIZIM.IS", "CRFSA.IS", "PNSUT.IS", "BANVT.IS",

    # Tech & Telecom (10)
    "ASELS.IS", "TCELL.IS", "TTKOM.IS", "SDTTR.IS", "VBTYZ.IS",
    "LOGO.IS", "INDES.IS", "NETAS.IS", "KAREL.IS", "ARDYZ.IS",

    # Mining & Metals (6)
    "KRDMD.IS", "CEMAS.IS", "ISGSY.IS", "SARKY.IS", "CELHA.IS", "BRSAN.IS",

    # Construction & Real Estate (6)
    "ENKAI.IS", "TKFEN.IS", "TURSG.IS", "OYAKC.IS", "CIMSA.IS", "BUCIM.IS",

    # Insurance & Finance (5)
    "ANSGR.IS", "AKGRT.IS", "TURSG.IS", "ANHYT.IS", "ISMEN.IS",

    # Healthcare & Pharma (5)
    "SELEC.IS", "DEVA.IS", "ECILC.IS", "LKMNH.IS", "MPARK.IS",

    # Chemicals & Materials (5)
    "SASA.IS", "AKSA.IS", "HEKTS.IS", "ALKIM.IS", "BAGFS.IS",

    # Tourism & Media (4)
    "MRGYO.IS", "TRGYO.IS", "VAKKO.IS", "DURDO.IS",

    # Other Notable BIST Stocks (13)
    "ASUZU.IS", "BERA.IS", "CANTE.IS", "DGNMO.IS", "ESEN.IS",
    "GENIL.IS", "GEDIK.IS", "GOODY.IS", "GOZDE.IS", "HURGZ.IS",
    "KLMSN.IS", "KONKA.IS", "KONYA.IS",
]

# Deduplicate
BIST_SYMBOLS = list(dict.fromkeys(BIST_SYMBOLS))

# ============================================================
# GLOBAL STOCKS — Expanded coverage (~215+ stocks)
# ============================================================
GLOBAL_SYMBOLS = [
    # US Tech Giants & FAANG+ (29)
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "NFLX",
    "AMD", "INTC", "AVGO", "QCOM", "CSCO", "ORCL", "ADBE", "CRM",
    "NOW", "SNOW", "PANW", "CRWD", "ZS", "DDOG", "NET", "MDB",
    "PLTR", "U", "TTD", "TWLO", "PYPL",

    # AI & Robotics (8)
    "SMCI", "ARM", "MRVL", "AI", "PATH", "IONQ", "RGTI", "BBAI",

    # Finance & Banks (19)
    "JPM", "V", "MA", "BAC", "WFC", "C", "GS", "MS", "BLK", "AXP",
    "SCHW", "USB", "PNC", "TFC", "COF", "STT", "SPGI", "MCO", "ICE",

    # Consumer & Retail (18)
    "WMT", "COST", "HD", "LOW", "TGT", "TJX", "NKE", "LULU",
    "SBUX", "MCD", "YUM", "CMG", "DPZ", "ROST", "ULTA", "DG",
    "DLTR", "BURL",

    # Consumer Products & Brands (10)
    "PG", "KO", "PEP", "PM", "MO", "CL", "KMB", "EL", "CLX", "CHD",

    # Healthcare & Pharma (20)
    "JNJ", "UNH", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR",
    "BMY", "AMGN", "GILD", "VRTX", "REGN", "CI", "CVS", "HUM",
    "ELV", "HCA", "MOH",

    # Biotech (6)
    "MRNA", "BNTX", "BIIB", "ALNY", "INCY", "BMRN",

    # Media & Entertainment (9)
    "DIS", "CMCSA", "WBD", "FOXA", "SPOT", "RBLX", "TTWO",
    "PARA", "LYV",

    # Industrial & Manufacturing (18)
    "BA", "CAT", "GE", "HON", "UNP", "UPS", "FDX", "LMT", "RTX",
    "NOC", "GD", "MMM", "EMR", "ITW", "ETN", "PH", "ROK", "DOV",

    # Energy & Oil (14)
    "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY",
    "HAL", "BKR", "DVN", "FANG", "KMI",

    # Automotive (8)
    "F", "GM", "TM", "HMC", "STLA", "RIVN", "LCID", "NIO",

    # Semiconductors & Hardware (16)
    "TXN", "ADI", "MCHP", "KLAC", "LRCX", "AMAT", "MU", "NXPI",
    "ON", "SWKS", "WOLF", "MPWR", "ENTG", "ACLS", "CRUS", "SYNA",

    # E-commerce & Payments (10)
    "SHOP", "MELI", "EBAY", "ETSY", "SE", "BABA", "JD", "PDD",
    "COIN", "SOFI",

    # Telecom (4)
    "T", "VZ", "TMUS", "CHTR",

    # Real Estate & REITs (10)
    "PLD", "AMT", "CCI", "EQIX", "SPG", "PSA", "O", "WELL", "DLR", "VICI",

    # Utilities (8)
    "NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "XEL",

    # Crypto-Related (5)
    "MSTR", "MARA", "RIOT", "CLSK", "HUT",

    # International Giants (12)
    "TSM", "ASML", "NVO", "UL", "SAP", "TTE", "SHEL", "BP",
    "BHP", "RIO", "SNY", "GSK",

    # Space & Defense (5)
    "RKLB", "ASTS", "LUNR", "KTOS", "LDOS",
]

# Deduplicate
GLOBAL_SYMBOLS = list(dict.fromkeys(GLOBAL_SYMBOLS))

# ============================================================
# COMMODITIES
# ============================================================
COMMODITIES_SYMBOLS = {
    "GC=F": "Gold (USD)",
    "SI=F": "Silver (USD)",
    "HG=F": "Copper",
    "CL=F": "Crude Oil WTI",
    "BZ=F": "Brent Crude Oil",
    "NG=F": "Natural Gas",
    "PL=F": "Platinum",
    "PA=F": "Palladium",
    "ZW=F": "Wheat",
    "ZC=F": "Corn",
    "ZS=F": "Soybeans",
    "CT=F": "Cotton",
    "KC=F": "Coffee",
}
