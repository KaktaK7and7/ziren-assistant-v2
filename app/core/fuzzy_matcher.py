from Levenshtein import distance

from app.voice.text_utils import normalize_text


def similarity(a: str, b: str) -> float:
    a = normalize_text(a)
    b = normalize_text(b)

    if not a or not b:
        return 0.0

    max_len = max(len(a), len(b))
    return 1.0 - (distance(a, b) / max_len)


def fuzzy_contains(text: str, variants: list[str], threshold: float = 0.78) -> bool:
    text = normalize_text(text)
    words = text.split()

    for variant in variants:
        variant = normalize_text(variant)

        if variant in text:
            return True

        for word in words:
            if similarity(word, variant) >= threshold:
                return True

    return False


def find_fuzzy_match(text: str, variants: list[str], threshold: float = 0.78) -> str | None:
    text = normalize_text(text)
    words = text.split()

    best_variant = None
    best_score = 0.0

    for variant in variants:
        variant = normalize_text(variant)

        if variant in text:
            return variant

        for word in words:
            score = similarity(word, variant)
            if score > best_score:
                best_score = score
                best_variant = variant

    if best_score >= threshold:
        return best_variant

    return None