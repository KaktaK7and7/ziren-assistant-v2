import re
from num2words import num2words


_PHONETIC_WORDS = {
    "ai": "эй-ай",
    "api": "эй-пи-ай",
    "browser": "браузер",
    "chatgpt": "чат-джи-пи-ти",
    "cyberpunk": "сайберпанк",
    "discord": "дискорд",
    "error": "эррор",
    "github": "гитхаб",
    "melissa": "мелисса",
    "next": "нэкст",
    "openai": "оупен-эй-ай",
    "pause": "поуз",
    "play": "плэй",
    "previous": "привиэс",
    "python": "пайтон",
    "railway": "рэйлвэй",
    "react": "риэкт",
    "screen": "скрин",
    "screenshot": "скриншот",
    "settings": "сэттингс",
    "spotify": "спотифай",
    "steam": "стим",
    "stop": "стоп",
    "tauri": "таури",
    "typescript": "тайпскрипт",
    "vpn": "ви-пи-эн",
    "windows": "уиндоус",
    "youtube": "ютуб",
    "ziren": "зайрен",
}

_LETTER_NAMES = {
    "a": "эй", "b": "би", "c": "си", "d": "ди", "e": "и",
    "f": "эф", "g": "джи", "h": "эйч", "i": "ай", "j": "джей",
    "k": "кей", "l": "эл", "m": "эм", "n": "эн", "o": "оу",
    "p": "пи", "q": "кью", "r": "ар", "s": "эс", "t": "ти",
    "u": "ю", "v": "ви", "w": "дабл-ю", "x": "экс", "y": "уай",
    "z": "зи",
}

_ENGLISH_SOUND_RULES = (
    ("tion", "шн"), ("sion", "жн"), ("tch", "ч"), ("igh", "ай"),
    ("sh", "ш"), ("ch", "ч"), ("ph", "ф"), ("th", "с"),
    ("ck", "к"), ("qu", "кв"), ("ee", "и"), ("oo", "у"),
    ("ea", "и"), ("ai", "эй"), ("ay", "эй"), ("oa", "оу"),
    ("oi", "ой"), ("oy", "ой"), ("ou", "ау"), ("ow", "ау"),
)

_LATIN_TO_CYRILLIC = str.maketrans({
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф",
    "g": "г", "h": "х", "i": "и", "j": "дж", "k": "к", "l": "л",
    "m": "м", "n": "н", "o": "о", "p": "п", "q": "к", "r": "р",
    "s": "с", "t": "т", "u": "у", "v": "в", "w": "у", "x": "кс",
    "y": "й", "z": "з",
})

_LATIN_WORD_RE = re.compile(
    r"(?<![\w@./\\:])([A-Za-z][A-Za-z'-]{0,39})(?![\w@./\\:])",
)


def normalize_text(text: str) -> str:
    return re.sub(r"[^\w\sёЁ]", "", text.lower()).strip()


def clean_text(text: str) -> str:
    text_with_spoken_pauses = re.sub(r"[-–—]+", " ", text)
    return re.sub(
        r"[^а-яА-ЯёЁa-zA-Z0-9.,!? ]",
        "",
        text_with_spoken_pauses,
    ).strip()


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


def _phonetic_latin_word(word: str) -> str:
    normalized = word.lower().replace("’", "'")
    dictionary_value = _PHONETIC_WORDS.get(normalized)

    if dictionary_value:
        return dictionary_value

    if word.isupper() and 2 <= len(word) <= 6:
        return "-".join(_LETTER_NAMES[letter] for letter in normalized)

    phonetic = normalized.replace("'", "")
    for source, target in _ENGLISH_SOUND_RULES:
        phonetic = phonetic.replace(source, target)

    return phonetic.translate(_LATIN_TO_CYRILLIC)


def transcribe_latin_for_russian_tts(text: str) -> str:
    """Prepare natural Latin words for Silero's Russian-only voice.

    URLs, e-mail addresses and file paths are deliberately left untouched so
    the visible reply can keep exact technical values. This transformation is
    applied only to the private TTS copy, not to chat history or memory.
    """

    return _LATIN_WORD_RE.sub(
        lambda match: _phonetic_latin_word(match.group(1)),
        str(text or ""),
    )


def replace_numbers_with_words(text: str, lang: str = "ru") -> str:
    def replacer(match):
        value = match.group(0)
        try:
            number = int(float(value))
            return num2words(number, lang=lang)
        except Exception:
            return value

    return re.sub(r"\b\d+(\.\d+)?\b", replacer, text)
