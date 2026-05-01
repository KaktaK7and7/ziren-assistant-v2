from enum import Enum


class ListeningMode(str, Enum):
    ALWAYS = "always"
    WAKE_WORD = "wake_word"