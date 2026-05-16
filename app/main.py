import json
import threading
import time
from getpass import getpass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from app.api.auth_client import AuthClient
from app.api.neuro_client import NeuroClient
from app.events.event_bus import emit_event, get_events
from app.features.feature_gate import FeatureGate
from app.modules.registry import create_default_registry
from app.router.command_router import CommandRouter
from app.storage.local_store import save_session
from app.voice.audio_state import AudioState
from app.voice.listening_mode import ListeningMode
from app.voice.stt_vosk import VoskSTT
from app.voice.tts_silero import SileroTTS
from app.core.log_bus import add_log, get_logs


BASE_DIR = Path(__file__).resolve().parent.parent
VOSK_MODEL_PATH = BASE_DIR / "models" / "vosk" / "vosk-model-small-ru-0.22"

LOCAL_API_HOST = "127.0.0.1"
LOCAL_API_PORT = 8787


class AssistantControlState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.running = True
        self.listening_enabled = True
        self.mode = "WAKE_WORD"

    def status(self) -> dict:
        with self.lock:
            return {
                "running": self.running,
                "listening": self.listening_enabled,
                "mode": self.mode,
            }

    def set_listening(self, value: bool) -> dict:
        with self.lock:
            self.listening_enabled = value
            return {
                "running": self.running,
                "listening": self.listening_enabled,
                "mode": self.mode,
            }

    def toggle_listening(self) -> dict:
        with self.lock:
            self.listening_enabled = not self.listening_enabled
            return {
                "running": self.running,
                "listening": self.listening_enabled,
                "mode": self.mode,
            }

    def is_listening(self) -> bool:
        with self.lock:
            return self.listening_enabled

    def stop(self) -> None:
        with self.lock:
            self.running = False
            self.listening_enabled = False


def start_local_api(control: AssistantControlState, stt: VoskSTT) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            return

        def send_json(self, data: dict, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")

            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:
            self.send_json({"ok": True})

        def do_GET(self) -> None:
            if self.path == "/health":
                self.send_json({"ok": True})
                return

            if self.path == "/status":
                self.send_json(control.status())
                return

            if self.path == "/logs":
                self.send_json({"logs": get_logs()})
                return

            if self.path == "/events":
                self.send_json({"events": get_events()})
                return

            self.send_json({"error": "not found"}, status=404)

        def do_POST(self) -> None:
            if self.path == "/listening/toggle":
                status = control.toggle_listening()

                if status["listening"]:
                    stt.resume()
                    print("🎤 Прослушка включена через GUI")
                    add_log("Прослушка включена", meta={"source": "gui"})
                    emit_event("listening.enabled", payload={"source": "gui"})
                else:
                    stt.pause()
                    print("🔇 Прослушка выключена через GUI")
                    add_log("Прослушка выключена", meta={"source": "gui"})
                    emit_event("listening.disabled", payload={"source": "gui"})

                self.send_json(status)
                return

            if self.path == "/listening/enable":
                status = control.set_listening(True)
                stt.resume()
                print("🎤 Прослушка включена через GUI")
                add_log("Прослушка включена", meta={"source": "gui"})
                emit_event("listening.enabled", payload={"source": "gui"})
                self.send_json(status)
                return

            if self.path == "/listening/disable":
                status = control.set_listening(False)
                stt.pause()
                print("🔇 Прослушка выключена через GUI")
                add_log("Прослушка выключена", meta={"source": "gui"})
                emit_event("listening.disabled", payload={"source": "gui"})
                self.send_json(status)
                return

            self.send_json({"error": "not found"}, status=404)

    server = ThreadingHTTPServer((LOCAL_API_HOST, LOCAL_API_PORT), Handler)

    threading.Thread(
        target=server.serve_forever,
        daemon=True,
    ).start()

    print(f"🌐 Local API: http://{LOCAL_API_HOST}:{LOCAL_API_PORT}")
    add_log("Local API запущен", meta={"url": f"http://{LOCAL_API_HOST}:{LOCAL_API_PORT}"})
    emit_event("local_api.started", payload={"url": f"http://{LOCAL_API_HOST}:{LOCAL_API_PORT}"})

    return server


def main() -> None:
    control = AssistantControlState()

    state = AudioState()
    add_log("Ассистент запущен")
    emit_event("assistant.started")

    state.set_mode(ListeningMode.WAKE_WORD)
    add_log("Режим WAKE_WORD")
    emit_event("assistant.mode.changed", payload={"mode": "WAKE_WORD"})

    auth = AuthClient()
    session = auth.get_saved_session()

    if not session.get("user_id"):
        print("🔐 Нужно войти в аккаунт.")
        add_log("Требуется вход в аккаунт", level="warn")

        email = input("Email: ").strip()
        password = getpass("Пароль: ")

        session = auth.login(email=email, password=password)

        print(f"✅ Вход выполнен: {session['username']}")
        add_log("Вход выполнен", meta={"username": session.get("username")})
    else:
        print(f"✅ Сессия найдена: {session.get('username')}")
        add_log("Сессия найдена", meta={"username": session.get("username")})

    neuro = NeuroClient(
        user_id=session["user_id"],
        session_id=session.get("session_id"),
    )
    add_log("NeuroClient готов", meta={"user_id": session.get("user_id")})
    emit_event("ai.client.ready")

    command_router = CommandRouter(
        registry=create_default_registry(),
        feature_gate=FeatureGate(),
    )
    add_log("CommandRouter готов")
    emit_event("command.router.ready")

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

    local_api_server = start_local_api(control, stt)

    def after_tts_finished() -> None:
        add_log("TTS закончил говорить")
        emit_event("tts.finished")
        state.ignore_stt_for(0.8)
        stt.clear_queue()

    def start_stop_listener() -> None:
        add_log("Слушатель стоп-слова запущен")

        threading.Thread(
            target=lambda: tts.stop() if stt.listen_for_stop() else None,
            daemon=True,
        ).start()

    add_log("Загрузка Vosk...")
    stt.load()
    add_log("Vosk готов")
    emit_event("stt.ready")

    add_log("Загрузка Silero...")
    tts.load()
    add_log("Silero готов")
    emit_event("tts.ready")

    print("🎤 Режим: WAKE_WORD")
    print("🧠 Нейросеть: мелисса")
    print("⚡ Команды: змея")
    print("🛑 Во время речи скажи: стоп")

    add_log("Ассистент готов к работе")
    emit_event("assistant.ready")

    last_wait_log = 0.0

    try:
        while True:
            if not control.is_listening():
                stt.clear_queue()
                time.sleep(0.15)
                continue

            now = time.time()

            if now - last_wait_log > 8:
                add_log("Ожидание голосового ввода", meta={"mode": control.status()["mode"]})
                last_wait_log = now

            text = stt.listen_once()

            if not control.is_listening():
                stt.clear_queue()
                continue

            if not text:
                continue

            current_mode = None

            if text.startswith("__command__:"):
                current_mode = "command"
                text = text.replace("__command__:", "", 1)
                emit_event("wake_word.detected", payload={"mode": "command", "word": "змея"})

            elif text.startswith("__ai__:"):
                current_mode = "ai"
                text = text.replace("__ai__:", "", 1)
                emit_event("wake_word.detected", payload={"mode": "ai", "word": "мелисса"})

            elif text == "__wake_command__":
                current_mode = "command"

                print("⚡ Змея услышала кодовое слово.")
                add_log("Wake word услышан", meta={"type": "command", "word": "змея"})
                emit_event("wake_word.detected", payload={"mode": "command", "word": "змея"})

                add_log("TTS начал говорить", meta={"source": "wake_command"})
                emit_event("tts.started", payload={"source": "wake_command"})
                tts.speak("Слушаю команду.", on_finish=after_tts_finished)
                continue

            elif text == "__wake_ai__":
                current_mode = "ai"

                print("🧠 Мелисса услышала кодовое слово.")
                add_log("Wake word услышан", meta={"type": "ai", "word": "мелисса"})
                emit_event("wake_word.detected", payload={"mode": "ai", "word": "мелисса"})

                add_log("TTS начал говорить", meta={"source": "wake_ai"})
                emit_event("tts.started", payload={"source": "wake_ai"})
                tts.speak("Я здесь.", on_finish=after_tts_finished)
                continue

            elif text == "__command_timeout__":
                print("⌛ Команда не поступила.")
                add_log("Команда не поступила", level="warn")

                add_log("TTS начал говорить", meta={"source": "command_timeout"})
                emit_event("tts.started", payload={"source": "command_timeout"})
                tts.speak("Долго думаешь.", on_finish=after_tts_finished)
                continue

            print(f"👤 Ты сказал: {text}")
            add_log("Речь распознана", meta={"text": text, "mode": current_mode})
            emit_event("speech.recognized", payload={"text": text, "mode": current_mode})

            if "выход" in text:
                print("👋 Завершаю.")
                add_log("Команда выхода получена")
                break

            if "тест" in text or "говори" in text:
                add_log("Запущен тест TTS", meta={"text": text})

                long_text = (
                    "Хорошо, начинаю замолчи длинную проверку голоса. "
                    "Сейчас я буду хватит говорить несколько стоп предложений подряд, "
                    "а ты можешь в любой момент сказать стоп. "
                    "Если всё стоп работает правильно, я должна хватит замолчать сразу, "
                    "не договаривая замолчи текущий текст до конца. "
                    "Это нужно для нормального голосового ассистента."
                )

                add_log("TTS начал говорить", meta={"source": "tts_test"})
                emit_event("tts.started", payload={"source": "tts_test"})
                tts.speak(long_text, on_finish=after_tts_finished)
                start_stop_listener()
                continue

            if current_mode == "command":
                print("⚡ Локальная команда")
                add_log("Локальная команда распознана", meta={"text": text})
                emit_event("command.received", payload={"text": text})

                route_result = command_router.route(text)

                if route_result:
                    response_text = route_result.response.text
                    add_log(
                        "Команда обработана модулем",
                        meta={
                            "text": text,
                            "feature_id": route_result.module.feature_id,
                        },
                    )
                    emit_event(
                        "command.module.executed",
                        payload={
                            "text": text,
                            "feature_id": route_result.module.feature_id,
                        },
                    )
                else:
                    response_text = "Команда пока не распознана."
                    add_log("Команда не распознана", level="warn", meta={"text": text})
                    emit_event("command.unknown", payload={"text": text}, level="warn")

                add_log("TTS начал говорить", meta={"source": "local_command"})
                emit_event("tts.started", payload={"source": "local_command"})
                tts.speak(response_text, on_finish=after_tts_finished)
                start_stop_listener()
                continue

            if current_mode == "ai":
                print("🧠 Отправляю в нейро-модуль...")
                add_log("AI-запрос отправлен", meta={"text": text})
                emit_event("ai.request.started", payload={"text": text})

                try:
                    answer = neuro.send_message(text)

                    session["session_id"] = neuro.session_id
                    save_session(session)

                    print(f"🤖 Мелисса: {answer}")
                    add_log("AI-ответ получен", meta={"answer": answer[:250]})
                    emit_event("ai.response.received", payload={"answer_preview": answer[:250]})

                    add_log("TTS начал говорить", meta={"source": "ai_answer"})
                    emit_event("tts.started", payload={"source": "ai_answer"})
                    tts.speak(answer, on_finish=after_tts_finished)
                    start_stop_listener()

                except Exception as e:
                    print(f"❌ Ошибка нейро-модуля: {e}")
                    add_log("Ошибка нейро-модуля", level="error", meta={"error": str(e)})
                    emit_event("ai.error", payload={"error": str(e)}, level="error")

                    add_log("TTS начал говорить", meta={"source": "neuro_error"})
                    emit_event("tts.started", payload={"source": "neuro_error"})
                    tts.speak(
                        "Не смогла связаться с нейро-модулем.",
                        on_finish=after_tts_finished,
                    )
                    start_stop_listener()

                continue

            print("⚠️ Неизвестный режим. Скажи 'мелисса' для нейросети или 'змея' для команд.")
            add_log("Неизвестный режим распознавания", level="warn", meta={"text": text})

    finally:
        add_log("Ассистент завершает работу")
        emit_event("assistant.stopping")

        control.stop()
        local_api_server.shutdown()
        state.shutdown.set()
        tts.stop()
        stt.close()


if __name__ == "__main__":
    main()
