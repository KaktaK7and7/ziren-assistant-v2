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
from app.core.fuzzy_matcher import find_fuzzy_match, similarity


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
        self.pending_wake_mode: str | None = None
        self.pending_wake_timeout_seconds = 5.0
        self.pending_wake_timeout_marker = "__command_timeout__"
        self.last_ai_listening_end_reason = ""
        self.last_ai_listening_started_speech = False

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
        self.pending_wake_mode = None
        self.pending_wake_timeout_marker = "__command_timeout__"
        self.state.wake_word_active.clear()
        self.clear_queue()
        print("🔇 STT поставлен на паузу.")

    def resume(self) -> None:
        self.paused = False
        self.pending_wake_mode = None
        self.pending_wake_timeout_marker = "__command_timeout__"
        self.clear_queue()
        print("🎤 STT снова активен.")

    def start_ai_followup(self, timeout_seconds: float = 5.0) -> None:
        self.pending_wake_mode = "ai"
        self.pending_wake_timeout_seconds = timeout_seconds
        self.pending_wake_timeout_marker = "__ai_followup_timeout__"
        self.state.wake_word_active.set()
        self.clear_queue()

    def listen_ai_until_silence(
        self,
        initial_speech_timeout_seconds: float = 8.0,
        silence_timeout_seconds: float = 3.0,
        max_duration_seconds: float = 60.0,
    ) -> str | None:
        if self.model is None:
            raise RuntimeError("VoskSTT.load() must be called first")

        self.last_ai_listening_end_reason = ""
        self.last_ai_listening_started_speech = False
        self.pending_wake_mode = None
        self.pending_wake_timeout_marker = "__command_timeout__"
        self.state.wake_word_active.clear()
        self.clear_queue()

        recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)
        started_at = time.time()
        last_speech_at: float | None = None
        final_chunks: list[str] = []

        while not self.state.shutdown.is_set():
            now = time.time()

            if self.paused:
                self.clear_queue()
                self.last_ai_listening_end_reason = "paused"
                return None

            if now - started_at >= max_duration_seconds:
                self.last_ai_listening_end_reason = "max_duration"
                return self._finish_ai_listening(recognizer, final_chunks)

            if last_speech_at is None:
                if now - started_at >= initial_speech_timeout_seconds:
                    self.last_ai_listening_end_reason = "initial_timeout"
                    self.clear_queue()
                    return "__ai_timeout__"
            elif now - last_speech_at >= silence_timeout_seconds:
                self.last_ai_listening_end_reason = "silence"
                return self._finish_ai_listening(recognizer, final_chunks)

            if self.state.ignore_regular_stt.is_set() or self.state.should_ignore_stt_now():
                self.clear_queue()
                time.sleep(0.05)
                continue

            try:
                audio = self.audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if recognizer.AcceptWaveform(audio):
                text = self._extract_text(recognizer.Result(), key="text")

                if not text:
                    continue

                final_chunks.append(text)
                last_speech_at = time.time()
                self.last_ai_listening_started_speech = True
                print(f"рџ§ѕ Vosk AI final: {text}")
                continue

            partial = self._extract_text(recognizer.PartialResult(), key="partial")

            if partial:
                last_speech_at = time.time()
                self.last_ai_listening_started_speech = True

        self.last_ai_listening_end_reason = "shutdown"
        return self._finish_ai_listening(recognizer, final_chunks)

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
                and now - command_wait_started_at >= self.pending_wake_timeout_seconds
            ):
                timeout_marker = self.pending_wake_timeout_marker
                self.state.wake_word_active.clear()
                self.pending_wake_mode = None
                self.pending_wake_timeout_seconds = 5.0
                self.pending_wake_timeout_marker = "__command_timeout__"
                self.clear_queue()
                return timeout_marker

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

                            self.pending_wake_mode = "command"
                            self.pending_wake_timeout_seconds = 5.0
                            self.pending_wake_timeout_marker = "__command_timeout__"
                            self.state.wake_word_active.set()
                            command_wait_started_at = time.time()
                            self.clear_queue()
                            return "__wake_command__"

                        if wake_type == "ai":
                            command_after_wake = self._remove_wake_word(text, wake_word)

                            if command_after_wake:
                                return f"__ai__:{command_after_wake}"

                            self.pending_wake_mode = "ai"
                            self.pending_wake_timeout_seconds = 5.0
                            self.pending_wake_timeout_marker = "__command_timeout__"
                            self.state.wake_word_active.set()
                            command_wait_started_at = time.time()
                            self.clear_queue()
                            return "__wake_ai__"

                        continue

                    mode = self.pending_wake_mode or "command"
                    self.state.wake_word_active.clear()
                    self.pending_wake_mode = None
                    self.pending_wake_timeout_seconds = 5.0
                    self.pending_wake_timeout_marker = "__command_timeout__"

                    if mode == "ai":
                        return f"__ai__:{text}"

                    return f"__command__:{text}"

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

    def _finish_ai_listening(
        self,
        recognizer: vosk.KaldiRecognizer,
        final_chunks: list[str],
    ) -> str | None:
        final_text = self._extract_text(recognizer.FinalResult(), key="text")

        if final_text:
            final_chunks.append(final_text)

        text = normalize_text(" ".join(final_chunks))
        self.clear_queue()
        return text or None

    def _extract_text(self, raw_json: str, key: str) -> str:
        try:
            data = json.loads(raw_json)
            return normalize_text(data.get(key, ""))
        except Exception:
            return ""

    def _contains_any(self, text: str, words: list[str]) -> bool:
        return any(word in text for word in words)

    def _find_wake_word(self, text: str) -> tuple[str | None, str | None]:
        normalized_text = normalize_text(text)
        text_words = normalized_text.split()
        wake_threshold = 0.72

        for variant in self.command_wake_words:
            if variant in normalized_text:
                return "command", variant

        for variant in self.ai_wake_words:
            if variant in normalized_text:
                return "ai", variant

        for word in text_words:
            command_match = find_fuzzy_match(
                text=word,
                variants=self.command_wake_words,
                threshold=wake_threshold,
            )
            if command_match:
                return "command", command_match

        for word in text_words:
            ai_match = find_fuzzy_match(
                text=word,
                variants=self.ai_wake_words,
                threshold=wake_threshold,
            )
            if ai_match:
                return "ai", ai_match

        return None, None

    def _remove_wake_word(self, text: str, wake_word: str) -> str:
        normalized_text = normalize_text(text)
        normalized_wake_word = normalize_text(wake_word)

        if normalized_wake_word in normalized_text:
            command = normalized_text.replace(normalized_wake_word, "", 1)
            return normalize_text(command)

        words = normalized_text.split()
        best_index = None
        best_score = 0.0

        for index, word in enumerate(words):
            score = similarity(word, normalized_wake_word)

            if score > best_score:
                best_score = score
                best_index = index

        if best_index is not None and best_score >= 0.72:
            words.pop(best_index)
            return normalize_text(" ".join(words))

        command = normalized_text.replace(normalized_wake_word, "", 1)
        return normalize_text(command)

    def close(self) -> None:
        self.state.shutdown.set()
        self.pending_wake_mode = None
        self.pending_wake_timeout_marker = "__command_timeout__"

        if self.stream:
            self.stream.stop()
            self.stream.close()

        print("👋 STT выключен.")
