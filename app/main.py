import json
import random
import threading
import time
from getpass import getpass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from app.app_launcher.cache import AppLauncherCache
from app.app_launcher.models import AppTarget
from app.api.auth_client import AuthClient
from app.api.neuro_client import NeuroClient
from app.events.event_bus import emit_event, get_events
from app.features.feature_gate import FeatureGate
from app.modules.registry import ModuleRegistry, create_default_registry
from app.router.command_router import CommandRouter
from app.settings.trigger_store import TriggerStore
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

AI_WAKE_RESPONSES = [
    "Я здесь.",
    "Слушаю тебя.",
    "Да, я рядом.",
    "Говори, я слушаю.",
    "Я с тобой.",
]


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


def start_local_api(
    control: AssistantControlState,
    stt: VoskSTT,
    registry: ModuleRegistry,
    trigger_store: TriggerStore,
) -> ThreadingHTTPServer:
    app_launcher_cache = AppLauncherCache()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            return

        def send_json(self, data: dict, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")

            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def send_bad_request(self, error: str) -> None:
            self.send_json({"ok": False, "error": error}, status=400)

        def read_json_body(self) -> dict | None:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return None

            if content_length <= 0:
                return None

            try:
                body = self.rfile.read(content_length)
                data = json.loads(body.decode("utf-8"))
            except Exception:
                return None

            if not isinstance(data, dict):
                return None

            return data

        def module_trigger_response(self, feature_id: str) -> dict | None:
            module = registry.get_module_by_feature_id(feature_id)

            if module is None:
                return None

            return registry.build_feature_trigger_response(module)

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

            if self.path == "/features/triggers":
                self.send_json({"features": registry.get_feature_trigger_data()})
                return

            if self.path == "/features/triggers/defaults":
                self.send_json({"features": registry.get_feature_trigger_defaults()})
                return

            if self.path == "/app-launcher/apps":
                self.send_json({"apps": app_launcher_cache.list_apps()})
                return

            self.send_json({"error": "not found"}, status=404)

        def do_POST(self) -> None:
            if self.path == "/features/triggers":
                data = self.read_json_body()

                if data is None:
                    self.send_bad_request("invalid json body")
                    return

                feature_id = data.get("feature_id")
                trigger_groups = data.get("trigger_groups")
                triggers = data.get("triggers")

                if not isinstance(feature_id, str) or not feature_id.strip():
                    self.send_bad_request("feature_id must be a non-empty string")
                    return

                module = registry.get_module_by_feature_id(feature_id)

                if module is None:
                    self.send_bad_request("unknown feature_id")
                    return

                if trigger_groups is not None:
                    if not isinstance(trigger_groups, dict):
                        self.send_bad_request("trigger_groups must be an object")
                        return

                    default_groups = module.get_default_trigger_groups()
                    groups_to_save: dict[str, list[str]] = {}

                    for action_id, group_triggers in trigger_groups.items():
                        if action_id not in default_groups:
                            self.send_bad_request(f"unknown action_id: {action_id}")
                            return

                        if not isinstance(group_triggers, list) or not all(
                            isinstance(trigger, str) for trigger in group_triggers
                        ):
                            self.send_bad_request(
                                "trigger_groups values must be lists of strings"
                            )
                            return

                        groups_to_save[action_id] = group_triggers

                    trigger_store.set_groups(feature_id, groups_to_save)
                else:
                    if not isinstance(triggers, list) or not all(
                        isinstance(trigger, str) for trigger in triggers
                    ):
                        self.send_bad_request("triggers must be a list of strings")
                        return

                    trigger_store.set(feature_id, triggers)

                feature = self.module_trigger_response(feature_id)

                if feature is None:
                    self.send_bad_request("unknown feature_id")
                    return

                self.send_json({"ok": True, "feature": feature})
                return

            if self.path == "/app-launcher/apps":
                data = self.read_json_body()

                if data is None:
                    self.send_bad_request("invalid json body")
                    return

                try:
                    original_target_id = str(data.get("target_id", "")).strip()
                    target = AppTarget(
                        target_id="",
                        name=str(data.get("name", "")).strip(),
                        type=str(data.get("type", "")).strip(),
                        path=data.get("path"),
                        appid=data.get("appid"),
                        spoken_name=data.get("spoken_name"),
                        source=str(data.get("source", "")),
                    )

                    if not target.type:
                        self.send_bad_request("type is required")
                        return

                    aliases = data.get("aliases", [])

                    if not isinstance(aliases, list) or not all(
                        isinstance(alias, str) for alias in aliases
                    ):
                        self.send_bad_request("aliases must be a list of strings")
                        return

                    app_launcher_cache.upsert_target_with_aliases(
                        target,
                        aliases,
                        original_target_id=original_target_id,
                    )
                    self.send_json({"ok": True, "apps": app_launcher_cache.list_apps()})
                except Exception as error:
                    self.send_bad_request(str(error))

                return

            if self.path == "/app-launcher/apps/cleanup":
                try:
                    app_launcher_cache.cleanup_duplicates()
                    self.send_json({"ok": True, "apps": app_launcher_cache.list_apps()})
                except Exception as error:
                    self.send_bad_request(str(error))

                return

            if self.path == "/app-launcher/aliases":
                data = self.read_json_body()

                if data is None:
                    self.send_bad_request("invalid json body")
                    return

                alias = data.get("alias")
                target_id = data.get("target_id")

                if not isinstance(alias, str) or not isinstance(target_id, str):
                    self.send_bad_request("alias and target_id are required")
                    return

                try:
                    app_launcher_cache.add_alias(alias, target_id)
                    self.send_json({"ok": True, "apps": app_launcher_cache.list_apps()})
                except Exception as error:
                    self.send_bad_request(str(error))

                return

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

        def do_DELETE(self) -> None:
            if self.path.startswith("/app-launcher/apps/"):
                target_id = unquote(self.path.removeprefix("/app-launcher/apps/"))

                if not target_id:
                    self.send_bad_request("target_id is required")
                    return

                app_launcher_cache.delete_target(target_id)
                self.send_json({"ok": True, "apps": app_launcher_cache.list_apps()})
                return

            if self.path == "/app-launcher/aliases":
                data = self.read_json_body()

                if data is None:
                    self.send_bad_request("invalid json body")
                    return

                alias = data.get("alias")

                if not isinstance(alias, str) or not alias.strip():
                    self.send_bad_request("alias is required")
                    return

                app_launcher_cache.delete_alias(alias)
                self.send_json({"ok": True, "apps": app_launcher_cache.list_apps()})
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

    trigger_store = TriggerStore()
    registry = create_default_registry(trigger_store=trigger_store)

    command_router = CommandRouter(
        registry=registry,
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

    local_api_server = start_local_api(control, stt, registry, trigger_store)
    ai_followup_waiting = False

    def after_tts_finished() -> None:
        add_log("TTS закончил говорить")
        emit_event("tts.finished")
        state.ignore_stt_for(0.8)
        stt.clear_queue()

    def after_ai_tts_finished() -> None:
        nonlocal ai_followup_waiting

        was_interrupted = state.was_tts_interrupted()
        after_tts_finished()

        if was_interrupted:
            ai_followup_waiting = False
            add_log("AI follow-up пропущен", meta={"reason": "tts_interrupted"})
            emit_event("ai.followup.skipped", payload={"reason": "tts_interrupted"})
            return

        ai_followup_waiting = True
        stt.start_ai_followup(timeout_seconds=5.0)
        add_log("AI follow-up режим включен", meta={"timeout_seconds": 5})
        emit_event("ai.followup.started", payload={"timeout_seconds": 5})

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

                if ai_followup_waiting:
                    ai_followup_waiting = False
                    add_log("AI follow-up фраза распознана", meta={"text": text})
                    emit_event("ai.followup.captured", payload={"text": text})
                else:
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
                tts.speak(random.choice(AI_WAKE_RESPONSES), on_finish=after_tts_finished)
                continue

            elif text == "__command_timeout__":
                print("⌛ Команда не поступила.")
                add_log("Команда не поступила", level="warn")
                emit_event("command.timeout", level="warn")
                continue

            elif text == "__ai_followup_timeout__":
                ai_followup_waiting = False
                print("⌛ AI follow-up timeout.")
                add_log("AI follow-up timeout")
                emit_event("ai.followup.timeout")
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
                    tts.speak(answer, on_finish=after_ai_tts_finished)
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
