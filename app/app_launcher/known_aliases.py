import re


KNOWN_ALIASES: dict[str, list[str]] = {
    "Counter-Strike 2": [
        "counter strike 2",
        "counter strike",
        "cs2",
        "кс",
        "кска",
        "контра",
        "контр страйк",
        "каэс",
    ],
    "Dota 2": ["dota 2", "dota", "дота", "доту"],
    "World of Tanks": [
        "world of tanks",
        "wot",
        "танки",
        "танчики",
        "вот",
        "ворлд оф танкс",
        "мир танков",
    ],
    "Everlasting Summer": ["everlasting summer", "бесконечное лето", "бл"],
    "Telegram": ["telegram", "телеграм", "телега", "телегу", "тг"],
    "Discord": ["discord", "дискорд", "дс"],
    "Steam": ["steam", "стим"],
    "Google Chrome": ["chrome", "google chrome", "хром", "гугл хром", "браузер"],
}


def _normalize(value: str) -> str:
    value = value.lower().replace("ё", "е")
    value = re.sub(r"[^\w\s]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def get_known_aliases_for_name(name: str) -> list[str]:
    normalized_name = _normalize(name)

    for known_name, aliases in KNOWN_ALIASES.items():
        normalized_known_name = _normalize(known_name)
        normalized_aliases = [_normalize(alias) for alias in aliases]

        if normalized_name == normalized_known_name or normalized_known_name in normalized_name:
            return list(dict.fromkeys(normalized_aliases))

        if len(normalized_name) >= 4 and normalized_name in normalized_known_name:
            return list(dict.fromkeys(normalized_aliases))

        if any(alias == normalized_name for alias in normalized_aliases):
            return list(dict.fromkeys(normalized_aliases))

    return []
