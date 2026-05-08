import json
import queue
import time
from pathlib import Path
from typing import Optional

import sounddevice as sd
import vosk

from app.voice.audio_state import AudioState
from app.voice.listening_mode import ListeningMode
from app.voice.text_utils import normalize_text
from app.core.fuzzy_matcher import find_fuzzy_match


class VoskSTT:
    def __init__(
        self,
        model_path: str | Path,
        state: AudioState,
        ai_wake_words: list[str] | None = None,
        command_wake_words: list[str] | None = None,
        stop_words: list[str] | None = None,
        sample_rate: int = 16000,
        block_size: int = 4000,
    ) -> None:
        self.model_path = Path(model_path)
        self.state = state

        self.ai_wake_words = [normalize_text(w) for w in (ai_wake_words or ["мелисса"])]
        self.command_wake_words = [normalize_text(w) for w in (command_wake_words or ["змея"])]
        self.stop_words = [normalize_text(w) for w in (stop_words or ["стоп", "замолчи", "хватит"])]

        self.sample_rate = sample_rate
        self.block_size = block_size

        self.model: Optional[vosk.Model] = None
        self.audio_queue: queue.Queue[bytes] = queue.Queue()
        self.stream: Optional[sd.RawInputStream] = None

        self.paused = False

    def load(self) -> None:
        if not self.model_path.exists():
            raise FileNotFoundError(f"Vosk model not found: {self.model_path}")

        print("🔄 Загружаю Vosk модель...")
        self.model = vosk.Model(str(self.model_path))

        self.stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            dtype="int16",
            channels=1,
            callback=self._audio_callback,
        )
        self.stream.start()

        if self.state.listening_mode == ListeningMode.ALWAYS:
            self.state.wake_word_active.set()

        print("✅ Vosk готов. Микрофон слушает.")

    def pause(self) -> None:
        self.paused = True
        self.state.wake_word_active.clear()
        self.clear_queue()
        print("🔇 STT поставлен на паузу.")

    def resume(self) -> None:
        self.paused = False
        self.clear_queue()
        print("🎤 STT снова активен.")

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if self.paused or self.state.shutdown.is_set():
            return

        if status:
            print(f"⚠️ Audio status: {status}")

        self.audio_queue.put(bytes(indata))

    def listen_once(self) -> str:
        if self.model is None:
            raise RuntimeError("VoskSTT.load() must be called first")

        if self.paused:
            self.clear_queue()
            time.sleep(0.1)
            return ""

        recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)

        last_listening_print = 0.0
        command_wait_started_at = 0.0
        command_timeout_seconds = 5.0

        while not self.state.shutdown.is_set():
            now = time.time()

            if self.paused:
                self.clear_queue()
                time.sleep(0.1)
                return ""

            if self.state.ignore_regular_stt.is_set() or self.state.should_ignore_stt_now():
                self.clear_queue()
                time.sleep(0.05)
                continue

            if (
                self.state.listening_mode == ListeningMode.WAKE_WORD
                and self.state.wake_word_active.is_set()
                and command_wait_started_at == 0.0
            ):
                command_wait_started_at = now

            if (
                self.state.listening_mode == ListeningMode.WAKE_WORD
                and self.state.wake_word_active.is_set()
                and command_wait_started_at > 0.0
                and now - command_wait_started_at >= command_timeout_seconds
            ):
                self.state.wake_word_active.clear()
                self.clear_queue()
                return "__command_timeout__"

            if now - last_listening_print >= 5:
                if self.state.listening_mode == ListeningMode.WAKE_WORD and not self.state.wake_word_active.is_set():
                    print("🎤 Жду кодовое слово...")
                else:
                    print("🎤 Слушаю команду...")
                last_listening_print = now

            try:
                audio = self.audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if self.paused:
                self.clear_queue()
                return ""

            if recognizer.AcceptWaveform(audio):
                text = self._extract_text(recognizer.Result(), key="text")

                if self.paused:
                    self.clear_queue()
                    return ""

                if text:
                    print(f"🧾 Vosk final: {text}")

                if not text:
                    continue

                if self.state.listening_mode == ListeningMode.ALWAYS:
                    return text

                if self.state.listening_mode == ListeningMode.WAKE_WORD:
                    if not self.state.wake_word_active.is_set():
                        wake_type, wake_word = self._find_wake_word(text)

                        if wake_type == "command":
                            command_after_wake = self._remove_wake_word(text, wake_word)

                            if command_after_wake:
                                return f"__command__:{command_after_wake}"

                            self.state.wake_word_active.set()
                            command_wait_started_at = time.time()
                            self.clear_queue()
                            return "__wake_command__"

                        if wake_type == "ai":
                            command_after_wake = self._remove_wake_word(text, wake_word)

                            if command_after_wake:
                                return f"__ai__:{command_after_wake}"

                            self.state.wake_word_active.set()
                            command_wait_started_at = time.time()
                            self.clear_queue()
                            return "__wake_ai__"

                        continue

                    self.state.wake_word_active.clear()
                    return text

        return ""

    def listen_for_stop(self) -> bool:
        if self.model is None:
            raise RuntimeError("VoskSTT.load() must be called first")

        recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)
        recognizer.SetWords(False)

        time.sleep(0.35)

        while self.state.is_speaking.is_set() and not self.state.shutdown.is_set():
            try:
                audio = self.audio_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            if recognizer.AcceptWaveform(audio):
                text = self._extract_text(recognizer.Result(), key="text")

                if not text:
                    continue

                if self._contains_any(text, self.stop_words):
                    if self.state.recent_tts_contains_any(self.stop_words):
                        print(f"🔇 Игнорирую свой стоп final: {text}")
                        recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)
                        recognizer.SetWords(False)
                        continue

                    return True

            else:
                partial = self._extract_text(recognizer.PartialResult(), key="partial")

                if not partial:
                    continue

                if self._contains_any(partial, self.stop_words):
                    if self.state.recent_tts_contains_any(self.stop_words):
                        print(f"🔇 Игнорирую свой стоп partial: {partial}")
                        recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)
                        recognizer.SetWords(False)
                        continue

                    return True

        return False

    def clear_queue(self) -> None:
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

    def _extract_text(self, raw_json: str, key: str) -> str:
        try:
            data = json.loads(raw_json)
            return normalize_text(data.get(key, ""))
        except Exception:
            return ""

    def _contains_any(self, text: str, words: list[str]) -> bool:
        return any(word in text for word in words)

    def _find_wake_word(self, text: str) -> tuple[str | None, str | None]:
        text_words = text.split()

        for word in text_words:
            command_match = find_fuzzy_match(
                text=word,
                variants=self.command_wake_words,
                threshold=0.75,
            )
            if command_match:
                return "command", command_match

            ai_match = find_fuzzy_match(
                text=word,
                variants=self.ai_wake_words,
                threshold=0.75,
            )
            if ai_match:
                return "ai", ai_match

        return None, None

    def _remove_wake_word(self, text: str, wake_word: str) -> str:
        command = text.replace(wake_word, "", 1)
        return normalize_text(command)

    def close(self) -> None:
        self.state.shutdown.set()

        if self.stream:
            self.stream.stop()
            self.stream.close()

        print("👋 STT выключен.")