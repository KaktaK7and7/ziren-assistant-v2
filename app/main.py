import threading
from getpass import getpass
from pathlib import Path

from app.api.auth_client import AuthClient
from app.api.neuro_client import NeuroClient
from app.storage.local_store import save_session
from app.voice.audio_state import AudioState
from app.voice.listening_mode import ListeningMode
from app.voice.stt_vosk import VoskSTT
from app.voice.tts_silero import SileroTTS


BASE_DIR = Path(__file__).resolve().parent.parent
VOSK_MODEL_PATH = BASE_DIR / "models" / "vosk" / "vosk-model-small-ru-0.22"


def main() -> None:
    state = AudioState()
    state.set_mode(ListeningMode.WAKE_WORD)

    auth = AuthClient()
    session = auth.get_saved_session()

    if not session.get("user_id"):
        print("🔐 Нужно войти в аккаунт.")
        email = input("Email: ").strip()
        password = getpass("Пароль: ")

        session = auth.login(email=email, password=password)
        print(f"✅ Вход выполнен: {session['username']}")
    else:
        print(f"✅ Сессия найдена: {session.get('username')}")

    neuro = NeuroClient(
        user_id=session["user_id"],
        session_id=session.get("session_id"),
    )

    stt = VoskSTT(
        model_path=VOSK_MODEL_PATH,
        state=state,
        ai_wake_words=["мелисса"],
        command_wake_words=["змея"],
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

    def start_stop_listener() -> None:
        threading.Thread(
            target=lambda: tts.stop() if stt.listen_for_stop() else None,
            daemon=True,
        ).start()

    stt.load()
    tts.load()

    print("🎤 Режим: WAKE_WORD")
    print("🧠 Нейросеть: мелисса")
    print("⚡ Команды: змея")
    print("🛑 Во время речи скажи: стоп")

    try:
        while True:
            text = stt.listen_once()

            if not text:
                continue

            current_mode = None

            if text.startswith("__command__:"):
                current_mode = "command"
                text = text.replace("__command__:", "", 1)

            elif text.startswith("__ai__:"):
                current_mode = "ai"
                text = text.replace("__ai__:", "", 1)

            elif text == "__wake_command__":
                current_mode = "command"
                print("⚡ Змея услышала кодовое слово.")
                tts.speak("Слушаю команду.", on_finish=after_tts_finished)
                continue

            elif text == "__wake_ai__":
                current_mode = "ai"
                print("🧠 Мелисса услышала кодовое слово.")
                tts.speak("Я здесь.", on_finish=after_tts_finished)
                continue

            elif text == "__command_timeout__":
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
                start_stop_listener()
                continue

            if current_mode == "command":
                print("⚡ Локальная команда")

                # Пока заглушка. Потом сюда подключим command router.
                tts.speak("Команда выполнена.", on_finish=after_tts_finished)
                start_stop_listener()
                continue

            if current_mode == "ai":
                print("🧠 Отправляю в нейро-модуль...")

                try:
                    answer = neuro.send_message(text)

                    session["session_id"] = neuro.session_id
                    save_session(session)

                    print(f"🤖 Мелисса: {answer}")
                    tts.speak(answer, on_finish=after_tts_finished)
                    start_stop_listener()

                except Exception as e:
                    print(f"❌ Ошибка нейро-модуля: {e}")
                    tts.speak(
                        "Не смогла связаться с нейро-модулем.",
                        on_finish=after_tts_finished,
                    )
                    start_stop_listener()

                continue

            print("⚠️ Неизвестный режим. Скажи 'мелисса' для нейросети или 'змея' для команд.")

    finally:
        state.shutdown.set()
        tts.stop()
        stt.close()


if __name__ == "__main__":
    main()