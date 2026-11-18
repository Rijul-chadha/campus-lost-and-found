"""Controlled vocabulary for categories, item types, colours and brands.

Both the LLM extractor and the rule-based fallback canonicalise into these values, so
matching compares like with like ("navy" vs "blue", "AirPods" vs "earbuds").
"""

from __future__ import annotations

# category -> item_type -> synonyms (lower-case, multi-word allowed)
CATALOG: dict[str, dict[str, list[str]]] = {
    "electronics": {
        "phone": ["phone", "iphone", "smartphone", "cellphone", "cell phone", "android phone",
                  "pixel phone", "galaxy phone", "mobile"],
        "laptop": ["laptop", "macbook", "chromebook", "thinkpad", "notebook computer"],
        "earbuds": ["earbuds", "airpods", "earphones", "ear buds", "galaxy buds", "pixel buds",
                    "airpod", "earpods", "buds case", "airpods case"],
        "headphones": ["headphones", "headset", "over-ear headphones"],
        "charger": ["charger", "charging cable", "power bank", "powerbank", "usb cable",
                    "adapter", "charging brick", "usb-c cable"],
        "tablet": ["tablet", "ipad", "kindle", "e-reader"],
        "calculator": ["calculator", "graphing calculator", "ti-84"],
        "smartwatch": ["smartwatch", "apple watch", "fitbit", "garmin watch"],
    },
    "cards": {
        "student_card": ["student card", "student id", "campus card", "id card", "onecard",
                         "t-card", "tcard", "student badge", "access card"],
        "drivers_license": ["driver's license", "drivers license", "driver's licence",
                            "drivers licence", "driving licence"],
        "bank_card": ["credit card", "debit card", "bank card", "visa card", "presto card",
                      "transit card"],
        "health_card": ["health card", "ohip card", "insurance card"],
        "passport": ["passport"],
    },
    "wallet": {
        "wallet": ["wallet", "cardholder", "card holder", "card case", "billfold", "coin purse"],
    },
    "keys": {
        "keys": ["keys", "key", "keychain", "key chain", "key ring", "keyring", "key fob", "fob",
                 "car key", "lanyard with keys"],
    },
    "bags": {
        "backpack": ["backpack", "rucksack", "bookbag", "book bag", "knapsack"],
        "bag": ["bag", "tote", "tote bag", "handbag", "purse", "duffel", "duffle", "gym bag",
                "laptop bag", "messenger bag", "shoulder bag", "fanny pack", "pouch"],
    },
    "clothing": {
        "jacket": ["jacket", "coat", "parka", "windbreaker", "puffer", "raincoat", "blazer"],
        "hoodie": ["hoodie", "sweatshirt", "sweater", "cardigan", "fleece", "pullover"],
        "hat": ["hat", "cap", "beanie", "toque", "baseball cap"],
        "scarf": ["scarf"],
        "gloves": ["gloves", "glove", "mittens", "mitts"],
        "shoes": ["shoes", "sneakers", "boots", "runners"],
    },
    "bottles": {
        "water_bottle": ["water bottle", "bottle", "hydro flask", "hydroflask", "tumbler",
                         "thermos",
                         "flask", "stanley cup", "nalgene", "travel mug", "mug"],
    },
    "accessories": {
        "glasses": ["glasses", "eyeglasses", "spectacles", "sunglasses", "glasses case"],
        "ring": ["ring", "wedding ring", "engagement ring"],
        "necklace": ["necklace", "chain", "pendant", "locket"],
        "bracelet": ["bracelet", "bangle"],
        "earrings": ["earring", "earrings", "stud earrings"],
        "watch": ["watch", "wristwatch"],
        "umbrella": ["umbrella"],
    },
    "stationery": {
        "notebook": ["notebook", "binder", "textbook", "book", "planner", "sketchbook", "journal"],
        "pencil_case": ["pencil case", "pen case", "pens", "pen"],
    },
    "sports": {
        "sports_gear": ["ball", "racket", "racquet", "yoga mat", "skates", "helmet", "gym gear"],
    },
    "other": {"other": []},
}

CATEGORIES: tuple[str, ...] = tuple(CATALOG.keys())
ITEM_TYPE_TO_CATEGORY: dict[str, str] = {
    item_type: cat for cat, types in CATALOG.items() for item_type in types
}

# Categories that commonly contain / are confused with each other. Not a veto between them.
COMPATIBLE_CATEGORIES: dict[str, frozenset[str]] = {
    "wallet": frozenset({"cards"}),
    "cards": frozenset({"wallet", "keys"}),  # student cards often live on key lanyards
    "keys": frozenset({"cards"}),
    "bags": frozenset({"stationery", "electronics"}),
    "accessories": frozenset({"electronics"}),  # watch vs smartwatch
    "electronics": frozenset({"accessories"}),
}

# Different item types that people genuinely describe interchangeably. Any other pair of
# different known item types is treated as a contradiction by the matcher.
CONFUSABLE_ITEM_TYPES: dict[frozenset[str], float] = {
    frozenset({"bag", "backpack"}): 0.7,
    frozenset({"jacket", "hoodie"}): 0.6,
    frozenset({"earbuds", "headphones"}): 0.6,
    frozenset({"watch", "smartwatch"}): 0.7,
    frozenset({"laptop", "tablet"}): 0.4,
    frozenset({"wallet", "student_card"}): 0.5,  # "lost my wallet" -> only the card turned up
    frozenset({"wallet", "bank_card"}): 0.5,
    frozenset({"keys", "student_card"}): 0.4,  # card on a key lanyard
    frozenset({"notebook", "pencil_case"}): 0.3,
    frozenset({"hat", "scarf"}): 0.2,
    frozenset({"necklace", "bracelet"}): 0.3,
}

# Item types whose photos/details are hidden from the public listing.
SENSITIVE_ITEM_TYPES: frozenset[str] = frozenset(
    {"student_card", "drivers_license", "bank_card", "health_card", "passport", "wallet"}
)

# colour word -> (canonical colour, family)
COLORS: dict[str, tuple[str, str]] = {
    "black": ("black", "black"), "jet black": ("black", "black"), "matte black": ("black", "black"),
    "white": ("white", "white"), "cream": ("cream", "white"), "ivory": ("cream", "white"),
    "off-white": ("cream", "white"),
    "gray": ("gray", "gray"), "grey": ("gray", "gray"), "charcoal": ("charcoal", "gray"),
    "dark gray": ("charcoal", "gray"), "dark grey": ("charcoal", "gray"),
    "silver": ("silver", "gray"), "space gray": ("charcoal", "gray"),
    "red": ("red", "red"), "maroon": ("maroon", "red"), "burgundy": ("maroon", "red"),
    "crimson": ("red", "red"), "wine": ("maroon", "red"),
    "orange": ("orange", "orange"), "coral": ("coral", "orange"),
    "yellow": ("yellow", "yellow"), "mustard": ("mustard", "yellow"), "gold": ("gold", "yellow"),
    "golden": ("gold", "yellow"),
    "green": ("green", "green"), "olive": ("olive", "green"), "lime": ("lime", "green"),
    "mint": ("mint", "green"), "forest green": ("dark green", "green"),
    "dark green": ("dark green", "green"), "khaki green": ("olive", "green"),
    "teal": ("teal", "blue"), "turquoise": ("teal", "blue"),
    "blue": ("blue", "blue"), "navy": ("navy", "blue"), "navy blue": ("navy", "blue"),
    "dark blue": ("navy", "blue"), "light blue": ("light blue", "blue"),
    "sky blue": ("light blue", "blue"), "baby blue": ("light blue", "blue"),
    "royal blue": ("blue", "blue"),
    "purple": ("purple", "purple"), "violet": ("purple", "purple"),
    "lavender": ("lavender", "purple"), "lilac": ("lavender", "purple"),
    "pink": ("pink", "pink"), "rose": ("pink", "pink"), "hot pink": ("pink", "pink"),
    "magenta": ("pink", "pink"), "rose gold": ("rose gold", "pink"),
    "brown": ("brown", "brown"), "tan": ("tan", "brown"), "beige": ("beige", "brown"),
    "khaki": ("beige", "brown"), "camel": ("tan", "brown"), "leather brown": ("brown", "brown"),
    "multicolor": ("multicolor", "multi"), "multicoloured": ("multicolor", "multi"),
    "multicolored": ("multicolor", "multi"), "rainbow": ("multicolor", "multi"),
    "clear": ("clear", "clear"), "transparent": ("clear", "clear"),
}
CANONICAL_COLOR_FAMILY: dict[str, str] = {canon: fam for canon, fam in COLORS.values()}

# Families that people mix up under bad lighting. Symmetric.
ADJACENT_COLOR_FAMILIES: dict[frozenset[str], float] = {
    frozenset({"black", "gray"}): 0.45,
    frozenset({"gray", "white"}): 0.35,
    frozenset({"blue", "purple"}): 0.35,
    frozenset({"blue", "green"}): 0.25,
    frozenset({"red", "pink"}): 0.45,
    frozenset({"red", "orange"}): 0.35,
    frozenset({"orange", "yellow"}): 0.35,
    frozenset({"orange", "brown"}): 0.3,
    frozenset({"yellow", "brown"}): 0.25,
    frozenset({"black", "blue"}): 0.2,  # navy in a dark room
}

# brand alias -> canonical brand
BRANDS: dict[str, str] = {
    "apple": "apple", "samsung": "samsung", "google": "google", "sony": "sony", "bose": "bose",
    "beats": "beats", "jbl": "jbl", "dell": "dell", "hp": "hp", "lenovo": "lenovo",
    "asus": "asus", "acer": "acer", "microsoft": "microsoft", "surface": "microsoft",
    "logitech": "logitech", "anker": "anker", "nike": "nike", "adidas": "adidas",
    "puma": "puma", "under armour": "under armour", "north face": "the north face",
    "the north face": "the north face", "lululemon": "lululemon", "herschel": "herschel",
    "jansport": "jansport", "patagonia": "patagonia", "columbia": "columbia",
    "canada goose": "canada goose", "arc'teryx": "arcteryx", "arcteryx": "arcteryx",
    "hydro flask": "hydro flask", "hydroflask": "hydro flask", "stanley": "stanley",
    "yeti": "yeti", "nalgene": "nalgene", "contigo": "contigo", "ray-ban": "ray-ban",
    "rayban": "ray-ban", "casio": "casio", "fossil": "fossil", "fitbit": "fitbit",
    "garmin": "garmin", "texas instruments": "texas instruments", "kindle": "amazon",
    "coach": "coach", "michael kors": "michael kors", "fjallraven": "fjallraven",
    "kanken": "fjallraven", "uniqlo": "uniqlo", "champion": "champion",
}

# Item words that imply a brand ("AirPods" -> apple).
IMPLIED_BRANDS: dict[str, str] = {
    "airpods": "apple", "airpod": "apple", "earpods": "apple", "iphone": "apple",
    "ipad": "apple", "macbook": "apple", "apple watch": "apple", "galaxy": "samsung",
    "galaxy buds": "samsung", "pixel": "google", "pixel buds": "google", "thinkpad": "lenovo",
    "ti-84": "texas instruments", "kanken": "fjallraven",
}
