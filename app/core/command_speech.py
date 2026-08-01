def choose_command_speech(
    default_response: str,
    reaction_ready: bool,
    reaction_text: str,
) -> tuple[str, bool]:
    normalized_reaction = str(reaction_text or "").strip()

    if reaction_ready and normalized_reaction:
        return normalized_reaction, True

    return str(default_response or "").strip(), False
