import threading
from pathlib import Path

from app.voice.audio_state import AudioState
from app.voice.listening_mode import ListeningMode
from app.voice.stt_vosk import VoskSTT
from app.voice.tts_silero import SileroTTS


BASE_DIR = Path(__file__).resolve().parent.parent
VOSK_MODEL_PATH = BASE_DIR / "models" / "vosk" / "vosk-model-small-ru-0.22"


def main() -> None:
    state = AudioState()
    state.set_mode(ListeningMode.WAKE_WORD)

    stt = VoskSTT(
        model_path=VOSK_MODEL_PATH,
        state=state,
        wake_words=["мелисса"],
        stop_words=["стоп", "замолчи", "хватит"],
    )

    tts = SileroTTS(
        state=state,
        speaker="xenia",
        model_id="v5_5_ru",
        sample_rate=48000,
    )

    def after_tts_finished() -> None:
        state.ignore_stt_for(0.8)
        stt.clear_queue()

    stt.load()
    tts.load()

    print("🎤 Режим: WAKE_WORD")
    print("🎤 Скажи: мелисса")
    print("🛑 Во время речи скажи: стоп")

    try:
        while True:
            text = stt.listen_once()

            if not text:
                continue

            if text == "__wake_word__":
                print("🟢 Мелисса услышала кодовое слово.")
                tts.speak("Слушаю.", on_finish=after_tts_finished)
                continue

            if text == "__command_timeout__":
                print("⌛ Команда не поступила.")
                tts.speak("Долго думаешь.", on_finish=after_tts_finished)
                continue

            print(f"👤 Ты сказал: {text}")

            if "выход" in text:
                print("👋 Завершаю.")
                break

            if "тест" in text or "говори" in text:
                long_text = (
                    "Хорошо, начинаю замолчи длинную проверку голоса. "
                    "Сейчас я буду хватит говорить несколько стоп предложений подряд, "
                    "а ты можешь в любой момент сказать стоп. "
                    "Если всё стоп работает правильно, я должна хватит замолчать сразу, "
                    "не договаривая замолчи текущий текст до конца. "
                    "Это нужно для нормального голосового ассистента."
                )

                tts.speak(long_text, on_finish=after_tts_finished)

                threading.Thread(
                    target=lambda: tts.stop() if stt.listen_for_stop() else None,
                    daemon=True,
                ).start()

            else:
                tts.speak("Команда распознана.", on_finish=after_tts_finished)

    finally:
        state.shutdown.set()
        tts.stop()
        stt.close()


if __name__ == "__main__":
    main()