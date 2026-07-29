import json
import random
import threading
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from app.app_launcher.cache import AppLauncherCache
from app.app_launcher.models import AppTarget
from app.api.auth_client import AuthClient
from app.api.local_security import (
    DEFAULT_LOCAL_API_ORIGINS,
    LOCAL_TOKEN_HEADER,
    get_local_auth_error,
    is_allowed_local_origin,
)
from app.api.neuro_client import NeuroAuthenticationError, NeuroClient
from app.config.settings import LOCAL_API_TOKEN_ENV, get_local_api_token
from app.events.event_bus import emit_event, get_events
from app.features.feature_gate import FeatureGate
from app.media_control.models import MusicPreset
from app.media_control.resolver import MediaResolver
from app.media_control.store import MusicPresetStore
from app.modules.registry import ModuleRegistry, create_default_registry
from app.router.command_router import CommandRouter
from app.settings.trigger_store import TriggerStore
from app.storage.local_store import load_session, save_session
from app.voice.audio_ducking import duck_volume, restore_volume
from app.voice.audio_state import AudioState
from app.voice.listening_mode import ListeningMode
from app.voice.stt_vosk import VoskSTT
from app.voice.tts_silero import SileroTTS
from app.core.log_bus import add_log, get_logs
from app.core.command_text import is_exit_command, is_tts_test_command


BASE_DIR = Path(__file__).resolve().parent.parent
VOSK_MODEL_PATH = BASE_DIR / "models" / "vosk" / "vosk-model-small-ru-0.22"

LOCAL_API_HOST = "127.0.0.1"
LOCAL_API_PORT = 8787
LOCAL_API_MAX_BODY_BYTES = 1024 * 1024
AI_LONG_LISTENING_SILENCE_TIMEOUT_SECONDS = 3.0
AI_LONG_LISTENING_MAX_DURATION_SECONDS = 60.0
AI_WAKE_INITIAL_SPEECH_TIMEOUT_SECONDS = 5.0
AI_FOLLOWUP_INITIAL_SPEECH_TIMEOUT_SECONDS = 5.0

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
    local_api_token: str,
) -> ThreadingHTTPServer:
    app_launcher_cache = AppLauncherCache()
    music_preset_store = MusicPresetStore()
    media_resolver = MediaResolver(music_preset_store)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:
            return

        def send_json(self, data: dict, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")

            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            origin = str(self.headers.get("Origin", "")).strip()

            if origin in DEFAULT_LOCAL_API_ORIGINS:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")

            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers",
                f"Content-Type, {LOCAL_TOKEN_HEADER}",
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def authorize_request(self) -> bool:
            auth_error = get_local_auth_error(
                self.headers.get("Origin"),
                self.headers.get(LOCAL_TOKEN_HEADER),
                local_api_token,
            )

            if auth_error is None:
                return True

            status, error = auth_error
            self.send_json({"ok": False, "error": error}, status=status)
            return False

        def send_bad_request(self, error: str) -> None:
            self.send_json({"ok": False, "error": error}, status=400)

        def read_json_body(self) -> dict | None:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return None

            if content_length <= 0 or content_length > LOCAL_API_MAX_BODY_BYTES:
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
            if not is_allowed_local_origin(self.headers.get("Origin")):
                self.send_json({"ok": False, "error": "Origin is not allowed"}, status=403)
                return

            self.send_json({"ok": True})

        def do_GET(self) -> None:
            if not self.authorize_request():
                return

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

            if self.path == "/media/presets":
                self.send_json(
                    {
                        "presets": [
                            asdict(preset)
                            for preset in music_preset_store.list_presets()
                        ]
                    }
                )
                return

            self.send_json({"error": "not found"}, status=404)

        def do_POST(self) -> None:
            if not self.authorize_request():
                return

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

            if self.path == "/media/presets":
                data = self.read_json_body()

                if data is None:
                    self.send_bad_request("invalid json body")
                    return

                aliases = data.get("aliases", [])

                if not isinstance(aliases, list) or not all(
                    isinstance(alias, str) for alias in aliases
                ):
                    self.send_bad_request("aliases must be a list of strings")
                    return

                try:
                    music_preset_store.save_preset(
                        MusicPreset(
                            preset_id=str(data.get("preset_id", "")).strip(),
                            name=str(data.get("name", "")).strip(),
                            url=str(data.get("url", "")).strip(),
                            aliases=aliases,
                            enabled=bool(data.get("enabled", True)),
                        )
                    )
                    self.send_json(
                        {
                            "ok": True,
                            "presets": [
                                asdict(preset)
                                for preset in music_preset_store.list_presets()
                            ],
                        }
                    )
                except Exception as error:
                    self.send_bad_request(str(error))

                return

            if self.path == "/media/presets/test":
                data = self.read_json_body()

                if data is None:
                    self.send_bad_request("invalid json body")
                    return

                url = str(data.get("url", "")).strip()
                result = media_resolver.test_preset(url)

                if result.status != "success":
                    self.send_bad_request(result.message)
                    return

                self.send_json({"ok": True, "message": result.message})
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
            if not self.authorize_request():
                return

            if self.path.startswith("/app-launcher/apps/"):
                target_id = unquote(self.path.removeprefix("/app-launcher/apps/"))

                if not target_id:
                    self.send_bad_request("target_id is required")
                    return

                app_launcher_cache.delete_target(target_id)
                self.send_json({"ok": True, "apps": app_launcher_cache.list_apps()})
                return

            if self.path.startswith("/media/presets/"):
                preset_id = unquote(self.path.removeprefix("/media/presets/"))

                if not preset_id:
                    self.send_bad_request("preset_id is required")
                    return

                music_preset_store.delete_preset(preset_id)
                self.send_json(
                    {
                        "ok": True,
                        "presets": [
                            asdict(preset)
                            for preset in music_preset_store.list_presets()
                        ],
                    }
                )
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
    local_api_token = get_local_api_token()

    if not local_api_token:
        raise RuntimeError(
            f"Local API token is missing ({LOCAL_API_TOKEN_ENV})"
        )

    control = AssistantControlState()

    state = AudioState()
    add_log("Ассистент запущен")
    emit_event("assistant.started")

    state.set_mode(ListeningMode.WAKE_WORD)
    add_log("Режим WAKE_WORD")
    emit_event("assistant.mode.changed", payload={"mode": "WAKE_WORD"})

    auth = AuthClient()
    user = auth.require_current_user()
    stored_session = load_session()
    user_id = str(user["id"])
    previous_user_id = str(stored_session.get("user_id", ""))
    session = {
        "user_id": user_id,
        "username": user.get("username", ""),
        "email": user.get("email", ""),
        "session_id": (
            stored_session.get("session_id")
            if previous_user_id == user_id
            else None
        ),
    }

    print(f"✅ Desktop-сессия подтверждена: {session['username']}")
    add_log(
        "Desktop-сессия подтверждена",
        meta={"username": session.get("username")},
    )

    neuro = NeuroClient(
        session_id=session.get("session_id"),
        desktop_token=auth.desktop_token,
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

    local_api_server = start_local_api(
        control,
        stt,
        registry,
        trigger_store,
        local_api_token,
    )
    ai_followup_waiting = False
    ai_long_listening_requested = False
    ai_long_listening_initial_timeout_seconds = AI_WAKE_INITIAL_SPEECH_TIMEOUT_SECONDS
    ai_long_listening_source = "wake"

    def request_ai_long_listening(source: str, initial_timeout_seconds: float) -> None:
        nonlocal ai_long_listening_requested
        nonlocal ai_long_listening_initial_timeout_seconds
        nonlocal ai_long_listening_source

        ai_long_listening_requested = True
        ai_long_listening_initial_timeout_seconds = initial_timeout_seconds
        ai_long_listening_source = source

    def after_tts_finished() -> None:
        add_log("TTS закончил говорить")
        emit_event("tts.finished")
        state.ignore_stt_for(0.8)
        stt.clear_queue()

    def after_wake_command_tts_finished() -> None:
        after_tts_finished()
        duck_volume(5)

    def after_wake_ai_tts_finished() -> None:
        add_log("TTS закончил говорить")
        emit_event("tts.finished")
        state.ignore_stt_for(0.3)
        stt.clear_queue()
        duck_volume(5)
        request_ai_long_listening("wake", AI_WAKE_INITIAL_SPEECH_TIMEOUT_SECONDS)

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
        request_ai_long_listening("followup", AI_FOLLOWUP_INITIAL_SPEECH_TIMEOUT_SECONDS)
        add_log(
            "AI follow-up режим включен",
            meta={
                "initial_timeout_seconds": AI_FOLLOWUP_INITIAL_SPEECH_TIMEOUT_SECONDS,
                "silence_timeout_seconds": AI_LONG_LISTENING_SILENCE_TIMEOUT_SECONDS,
                "max_duration_seconds": AI_LONG_LISTENING_MAX_DURATION_SECONDS,
            },
        )
        emit_event(
            "ai.followup.started",
            payload={
                "initial_timeout_seconds": AI_FOLLOWUP_INITIAL_SPEECH_TIMEOUT_SECONDS,
                "silence_timeout_seconds": AI_LONG_LISTENING_SILENCE_TIMEOUT_SECONDS,
                "max_duration_seconds": AI_LONG_LISTENING_MAX_DURATION_SECONDS,
            },
        )

    def start_stop_listener() -> None:
        add_log("Слушатель стоп-слова запущен")

        threading.Thread(
            target=lambda: tts.stop() if stt.listen_for_stop() else None,
            daemon=True,
        ).start()

    def wait_for_tts_to_finish() -> None:
        while state.is_speaking.is_set() and not state.shutdown.is_set():
            if not control.is_listening():
                break

            time.sleep(0.05)

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
                restore_volume()
                stt.clear_queue()
                time.sleep(0.15)
                continue

            now = time.time()

            if now - last_wait_log > 8:
                add_log("Ожидание голосового ввода", meta={"mode": control.status()["mode"]})
                last_wait_log = now

            current_mode = None

            if ai_long_listening_requested:
                ai_long_listening_requested = False
                duck_volume(5)
                add_log(
                    "AI слушает до паузы",
                    meta={
                        "source": ai_long_listening_source,
                        "initial_timeout_seconds": ai_long_listening_initial_timeout_seconds,
                        "silence_timeout_seconds": AI_LONG_LISTENING_SILENCE_TIMEOUT_SECONDS,
                        "max_duration_seconds": AI_LONG_LISTENING_MAX_DURATION_SECONDS,
                    },
                )
                emit_event(
                    "ai.long_listening.started",
                    payload={
                        "source": ai_long_listening_source,
                        "initial_timeout_seconds": ai_long_listening_initial_timeout_seconds,
                        "silence_timeout_seconds": AI_LONG_LISTENING_SILENCE_TIMEOUT_SECONDS,
                        "max_duration_seconds": AI_LONG_LISTENING_MAX_DURATION_SECONDS,
                    },
                )
                text = stt.listen_ai_until_silence(
                    initial_speech_timeout_seconds=ai_long_listening_initial_timeout_seconds,
                    silence_timeout_seconds=AI_LONG_LISTENING_SILENCE_TIMEOUT_SECONDS,
                    max_duration_seconds=AI_LONG_LISTENING_MAX_DURATION_SECONDS,
                )

                if stt.last_ai_listening_started_speech:
                    add_log("AI речь началась")

                if text == "__ai_timeout__" or not text:
                    ai_followup_waiting = False
                    restore_volume()
                    add_log("AI команда не поступила", level="warn")
                    emit_event("ai.timeout", level="warn")

                    if ai_long_listening_source == "followup":
                        emit_event("ai.followup.timeout", level="warn")

                    continue

                if stt.last_ai_listening_end_reason == "max_duration":
                    add_log(
                        "AI речь завершена по лимиту",
                        level="warn",
                        meta={"text": text},
                    )
                else:
                    add_log("AI речь завершена по паузе", meta={"text": text})

                emit_event(
                    "ai.long_listening.finished",
                    payload={
                        "source": ai_long_listening_source,
                        "reason": stt.last_ai_listening_end_reason,
                        "text": text,
                    },
                )
                current_mode = "ai"
                restore_volume()

                if ai_followup_waiting:
                    ai_followup_waiting = False
                    add_log("AI follow-up фраза распознана", meta={"text": text})
                    emit_event("ai.followup.captured", payload={"text": text})
            else:
                text = stt.listen_once()

            if not control.is_listening():
                restore_volume()
                stt.clear_queue()
                continue

            if not text:
                continue

            if current_mode is None and text.startswith("__command__:"):
                duck_volume(5)
                current_mode = "command"
                text = text.replace("__command__:", "", 1)
                emit_event("wake_word.detected", payload={"mode": "command", "word": "змея"})
                restore_volume()

            elif text.startswith("__ai__:"):
                duck_volume(5)
                current_mode = "ai"
                text = text.replace("__ai__:", "", 1)

                if ai_followup_waiting:
                    ai_followup_waiting = False
                    add_log("AI follow-up фраза распознана", meta={"text": text})
                    emit_event("ai.followup.captured", payload={"text": text})
                else:
                    emit_event("wake_word.detected", payload={"mode": "ai", "word": "мелисса"})
                restore_volume()

            elif text == "__wake_command__":
                current_mode = "command"
                duck_volume(5)

                print("⚡ Змея услышала кодовое слово.")
                add_log("Wake word услышан", meta={"type": "command", "word": "змея"})
                emit_event("wake_word.detected", payload={"mode": "command", "word": "змея"})

                add_log("TTS начал говорить", meta={"source": "wake_command"})
                emit_event("tts.started", payload={"source": "wake_command"})
                restore_volume()
                tts.speak("Слушаю команду.", on_finish=after_wake_command_tts_finished)
                continue

            elif text == "__wake_ai__":
                current_mode = "ai"
                duck_volume(5)

                print("🧠 Мелисса услышала кодовое слово.")
                add_log("Wake word услышан", meta={"type": "ai", "word": "мелисса"})
                emit_event("wake_word.detected", payload={"mode": "ai", "word": "мелисса"})

                add_log("TTS начал говорить", meta={"source": "wake_ai"})
                emit_event("tts.started", payload={"source": "wake_ai"})
                restore_volume()
                tts.speak(random.choice(AI_WAKE_RESPONSES), on_finish=after_wake_ai_tts_finished)
                wait_for_tts_to_finish()
                continue

            elif text == "__command_timeout__":
                restore_volume()
                print("⌛ Команда не поступила.")
                add_log("Команда не поступила", level="warn")
                emit_event("command.timeout", level="warn")
                continue

            elif text == "__ai_followup_timeout__":
                ai_followup_waiting = False
                restore_volume()
                print("⌛ AI follow-up timeout.")
                add_log("AI follow-up timeout")
                emit_event("ai.followup.timeout")
                continue

            print(f"👤 Ты сказал: {text}")
            add_log("Речь распознана", meta={"text": text, "mode": current_mode})
            emit_event("speech.recognized", payload={"text": text, "mode": current_mode})

            if current_mode == "command":
                print("⚡ Локальная команда")
                add_log("Локальная команда распознана", meta={"text": text})
                emit_event("command.received", payload={"text": text})

                if is_exit_command(text):
                    print("👋 Завершаю.")
                    add_log("Команда выхода получена")
                    break

                if is_tts_test_command(text):
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
                    restore_volume()
                    tts.speak(long_text, on_finish=after_tts_finished)
                    start_stop_listener()
                    continue

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
                restore_volume()
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
                    restore_volume()
                    tts.speak(answer, on_finish=after_ai_tts_finished)
                    start_stop_listener()
                    wait_for_tts_to_finish()

                except NeuroAuthenticationError as e:
                    print(f"❌ Desktop-сессия устарела: {e}")
                    add_log(
                        "Требуется повторный вход в Ziren",
                        level="error",
                        meta={"error": str(e)},
                    )
                    emit_event(
                        "ai.authentication_required",
                        payload={"error": str(e)},
                        level="error",
                    )

                    add_log("TTS начал говорить", meta={"source": "auth_error"})
                    emit_event("tts.started", payload={"source": "auth_error"})
                    restore_volume()
                    tts.speak(
                        "Сессия Ziren устарела. Перезайди в аккаунт.",
                        on_finish=after_tts_finished,
                    )
                    start_stop_listener()

                except Exception as e:
                    print(f"❌ Ошибка нейро-модуля: {e}")
                    add_log("Ошибка нейро-модуля", level="error", meta={"error": str(e)})
                    emit_event("ai.error", payload={"error": str(e)}, level="error")

                    add_log("TTS начал говорить", meta={"source": "neuro_error"})
                    emit_event("tts.started", payload={"source": "neuro_error"})
                    restore_volume()
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
        restore_volume()
        local_api_server.shutdown()
        state.shutdown.set()
        tts.stop()
        stt.close()


if __name__ == "__main__":
    main()
