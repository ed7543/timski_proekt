"""Shared slug generation - best-effort Cyrillic -> Latin transliteration
plus ASCII fallback, used anywhere a human-entered name needs to become a
URL-safe slug (course submissions, the ingestion pipeline)."""

_CYRILLIC_TABLE = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "ѓ": "gj", "е": "e",
    "ж": "zh", "з": "z", "ѕ": "dz", "и": "i", "ј": "j", "к": "k", "л": "l",
    "љ": "lj", "м": "m", "н": "n", "њ": "nj", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "ќ": "kj", "у": "u", "ф": "f", "х": "h", "ц": "c",
    "ч": "ch", "џ": "dzh", "ш": "sh",
}


def slugify(name: str) -> str:
    """Best-effort Cyrillic -> Latin slugify. Not guaranteed to match any
    external source's own slugs - just a readable, URL-safe identifier
    derived from a human-entered name."""
    out = []
    for ch in name.lower():
        if ch in _CYRILLIC_TABLE:
            out.append(_CYRILLIC_TABLE[ch])
        elif ch.isalnum():
            out.append(ch)
        elif ch in " -_/":
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")
