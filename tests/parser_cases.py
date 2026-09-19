"""Synthetic test messages for the parser. Replace/extend with real customer messages over time.

Each case: (message, pending_items_or_None, expected_intent, expected_items)
expected_items maps product_id -> packs. Use the key None for an unknown flavour,
and the value None for an unknown quantity. For follow-ups, the value is (action, packs).
"""

P = [{"product_id": "masala", "packs": 3, "raw_text": "3 masala", "confidence": 0.9},
     {"product_id": "ginger", "packs": 2, "raw_text": "2 adrak", "confidence": 0.9}]

CASES = [
    # --- English, clean
    ("3 packs masala and 2 packs ginger", None, "order", {"masala": 3, "ginger": 2}),
    ("Hi, please send 5 cardamom, 5 karak, 2 coffee", None, "order", {"cardamom": 5, "karak": 5, "coffee": 2}),
    ("10 classic", None, "order", {"classic": 10}),
    ("need 4 pink chai packs", None, "order", {"pink": 4}),
    ("Order: Masala - 6, Classic - 6, Coffee - 3", None, "order", {"masala": 6, "classic": 6, "coffee": 3}),
    ("two masala three ginger", None, "order", {"masala": 2, "ginger": 3}),
    ("1 pack each of masala, ginger and cardamom", None, "order", {"masala": 1, "ginger": 1, "cardamom": 1}),
    ("send me 12 pkt karak", None, "order", {"karak": 12}),
    ("7 regular 3 kashmiri", None, "order", {"classic": 7, "pink": 3}),
    ("2 plain tea packs and 2 coffee", None, "order", {"classic": 2, "coffee": 2}),
    # --- English, misspelled
    ("3 msala 2 gnger", None, "order", {"masala": 3, "ginger": 2}),
    ("5 cardmom 5 karrak", None, "order", {"cardamom": 5, "karak": 5}),
    ("4 cofee 4 clasic", None, "order", {"coffee": 4, "classic": 4}),
    ("6 pnk chai", None, "order", {"pink": 6}),
    ("massala 8 pax", None, "order", {"masala": 8}),
    # --- Roman Punjabi
    ("3 masale wali te 2 adrak wali bhej deo", None, "order", {"masala": 3, "ginger": 2}),
    ("do dabbe elaichi", None, "order", {"cardamom": 2}),
    ("panj pack kadak te tin pack coffee", None, "order", {"karak": 5, "coffee": 3}),
    ("sat sri akal ji, 4 ilaichi 4 adrak bhejna", None, "order", {"cardamom": 4, "ginger": 4}),
    ("veer ji 10 sada chai de pack chahide", None, "order", {"classic": 10}),
    ("gulabi chai 2 pack", None, "order", {"pink": 2}),
    ("char masala char adrak char elachi", None, "order", {"masala": 4, "ginger": 4, "cardamom": 4}),
    ("ik dabba kaafi da", None, "order", {"coffee": 1}),
    ("che pack kadak chai bhej dena kal", None, "order", {"karak": 6}),
    ("das pack masala, ath pack adrak", None, "order", {"masala": 10, "ginger": 8}),
    ("bhaji 3 pkt adrk wali 2 pkt ilachi", None, "order", {"ginger": 3, "cardamom": 2}),
    ("masala 5 adrak 5 elaichi 5 pink 5 karak 5 classic 5 coffee 5", None, "order",
     {"masala": 5, "ginger": 5, "cardamom": 5, "pink": 5, "karak": 5, "classic": 5, "coffee": 5}),
    ("paji normal wali 6 te kashmiri 2", None, "order", {"classic": 6, "pink": 2}),
    # --- Gurmukhi
    ("3 ਪੈਕ ਮਸਾਲਾ ਤੇ 2 ਪੈਕ ਅਦਰਕ", None, "order", {"masala": 3, "ginger": 2}),
    ("ਦੋ ਡੱਬੇ ਇਲਾਇਚੀ ਭੇਜ ਦਿਓ", None, "order", {"cardamom": 2}),
    ("ਪੰਜ ਪੈਕ ਕੜਕ ਚਾਹੀਦੇ ਨੇ", None, "order", {"karak": 5}),
    ("ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ ਜੀ, ਚਾਰ ਮਸਾਲਾ ਚਾਰ ਕੌਫੀ", None, "order", {"masala": 4, "coffee": 4}),
    ("ਗੁਲਾਬੀ ਚਾਹ 3 ਪੈਕ", None, "order", {"pink": 3}),
    ("ਕਲਾਸਿਕ 10 ਪੈਕ, ਅਦਰਕ ਵਾਲੀ 6 ਪੈਕ", None, "order", {"classic": 10, "ginger": 6}),
    ("ਤਿੰਨ ਮਸਾਲੇ ਵਾਲੀ ਤੇ ਇੱਕ ਕੌਫੀ", None, "order", {"masala": 3, "coffee": 1}),
    ("ਦਸ ਪੈਕ ਸਾਦੀ ਚਾਹ", None, "order", {"classic": 10}),
    # --- Mixed script / language
    ("3 pack ਮਸਾਲਾ and 2 adrak", None, "order", {"masala": 3, "ginger": 2}),
    ("please bhej do 5 elaichi te 5 ਕੜਕ", None, "order", {"cardamom": 5, "karak": 5}),
    ("kal tak 4 coffee te ਦੋ pink chahide", None, "order", {"coffee": 4, "pink": 2}),
    # --- Unknown flavour / quantity: must be flagged, never guessed
    ("5 packs chai", None, "order", {None: 5}),
    ("10 pack bhej do", None, "order", {None: 10}),
    ("ਪੰਜ ਪੈਕ ਚਾਹ", None, "order", {None: 5}),
    ("3 masala and 2 lemon tea", None, "order", {"masala": 3, None: 2}),
    ("2 green tea", None, "order", {None: 2}),
    ("masala te adrak bhej do", None, "order", {"masala": None, "ginger": None}),
    ("send some cardamom", None, "order", {"cardamom": None}),
    ("4 tulsi wali", None, "order", {None: 4}),
    # --- Follow-ups with a pending order
    ("also 2 elaichi", P, "follow_up", {"cardamom": ("add", 2)}),
    ("2 hor masala pa deo", P, "follow_up", {"masala": ("add", 2)}),
    ("make it 5 masala instead of 3", P, "follow_up", {"masala": ("set", 5)}),
    ("adrak 2 di jagah 4 kar do", P, "follow_up", {"ginger": ("set", 4)}),
    ("ginger rehn do, cancel that one only", P, "follow_up", {"ginger": ("remove", None)}),
    ("ਨਾਲ 3 ਪੈਕ ਕੌਫੀ ਵੀ", P, "follow_up", {"coffee": ("add", 3)}),
    ("and one karak", P, "follow_up", {"karak": ("add", 1)}),
    # --- Cancel
    ("cancel", P, "cancel", {}),
    ("order cancel kar do ji", P, "cancel", {}),
    ("rehn do, nahi chahida hun", P, "cancel", {}),
    ("ਆਰਡਰ ਕੈਂਸਲ ਕਰ ਦਿਓ", P, "cancel", {}),
    ("pls cancel my order", P, "cancel", {}),
    # --- Same as last time
    ("same as last time", None, "same_as_last", {}),
    ("pehle wala order hi bhej do", None, "same_as_last", {}),
    ("ਪਹਿਲਾਂ ਵਾਲਾ ਆਰਡਰ ਹੀ ਭੇਜ ਦਿਓ", None, "same_as_last", {}),
    ("the usual please", None, "same_as_last", {}),
    ("ohi pichli vaar wala", None, "same_as_last", {}),
    # --- Non-order
    ("hello", None, "non_order", {}),
    ("sat sri akal ji", None, "non_order", {}),
    ("when will my delivery come?", None, "non_order", {}),
    ("payment bhej diti hai", None, "non_order", {}),
    ("delivery kado aau gi?", None, "non_order", {}),
    ("thank you", None, "non_order", {}),
    ("ਧੰਨਵਾਦ ਜੀ", None, "non_order", {}),
    ("last order vich ik pack ghat si", None, "non_order", {}),
    ("what is the price of masala?", None, "non_order", {}),
    ("ok", P, "non_order", {}),
    ("call me", None, "non_order", {}),
]
