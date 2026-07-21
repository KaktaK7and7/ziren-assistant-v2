EXIT_COMMANDS = {
    "выход",
    "выйти",
    "заверши работу",
    "закрой ассистента",
}

TTS_TEST_COMMANDS = {
    "тест",
    "говори",
    "тест голоса",
    "проверка голоса",
}


def normalize_command_text(text: str) -> str:
    return " ".join(text.casefold().split())


def is_exit_command(text: str) -> bool:
    return normalize_command_text(text) in EXIT_COMMANDS


def is_tts_test_command(text: str) -> bool:
    return normalize_command_text(text) in TTS_TEST_COMMANDS
