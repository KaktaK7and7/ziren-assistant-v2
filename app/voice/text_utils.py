import re
from num2words import num2words


def normalize_text(text: str) -> str:
    return re.sub(r"[^\w\sёЁ]", "", text.lower()).strip()


def clean_text(text: str) -> str:
    return re.sub(r"[^а-яА-ЯёЁa-zA-Z0-9.,!? ]", "", text).strip()


def detect_language(text: str) -> str:
    return "en" if re.search(r"[a-zA-Z]", text) else "ru"


def split_text_by_language(text: str) -> list[tuple[str, str]]:
    parts = re.findall(r"[a-zA-Z]+|[^a-zA-Z]+", text)
    return [(part, detect_language(part)) for part in parts if part.strip()]


def split_long_text(text: str, max_length: int = 80) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) <= max_length:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            current = sentence

    if current:
        chunks.append(current)

    return chunks


def replace_numbers_with_words(text: str, lang: str = "ru") -> str:
    def replacer(match):
        value = match.group(0)
        try:
            number = int(float(value))
            return num2words(number, lang=lang)
        except Exception:
            return value

    return re.sub(r"\b\d+(\.\d+)?\b", replacer, text)