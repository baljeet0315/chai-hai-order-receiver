"""The product catalog: 7 flavours and what customers call them.

For now this lives in code. In Phase 2 it moves to the Supabase
`products` and `product_aliases` tables, and this file becomes the seed data.
"""

# product_id -> list of aliases (any script, any spelling)
CATALOG: dict[str, list[str]] = {
    "masala":   ["masala", "masale wali", "ਮਸਾਲਾ"],
    "ginger":   ["ginger", "adrak", "adrak wali", "ਅਦਰਕ"],
    "cardamom": ["cardamom", "elaichi", "ilaichi", "elachi", "ਇਲਾਇਚੀ"],
    "pink":     ["pink", "pink chai", "kashmiri", "gulabi"],
    "karak":    ["karak", "kadak", "kadak chai", "ਕੜਕ"],
    "classic":  ["classic", "regular", "plain", "sada", "normal"],
    "coffee":   ["coffee", "kaafi", "ਕੌਫੀ"],
}

PRODUCT_IDS = set(CATALOG.keys())

# Any line with more packs than this gets flagged for the owner.
MAX_PACKS_SANITY_LIMIT = 100
