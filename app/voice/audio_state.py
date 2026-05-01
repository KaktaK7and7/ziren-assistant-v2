import time
from threading import Event, Lock

from app.voice.listening_mode import ListeningMode
from app.voice.text_utils import normalize_text


class AudioState:
    def __init__(self) -> None:
        self.is_speaking = Event()
        self.stop_speaking = Event()
        self.ignore_regular_stt = Event()
        self.shutdown = Event()

        self.listening_mode = ListeningMode.ALWAYS
        self.wake_word_active = Event()

        self.current_tts_text = ""
        self.current_tts_chunk = ""
        self.recent_tts_chunks: list[tuple[str, float]] = []
        self.current_tts_lock = Lock()

        self.echo_ignore_seconds = 2.0

        # Дополнительная защита:
        # после окончания TTS ещё немного игнорируем STT,
        # чтобы не распознать хвост собственного голоса.
        self.ignore_stt_until = 0.0

    def set_mode(self, mode: ListeningMode) -> None:
        self.listening_mode = mode

        if mode == ListeningMode.ALWAYS:
            self.wake_word_active.set()
        else:
            self.wake_word_active.clear()

    def ignore_stt_for(self, seconds: float) -> None:
        self.ignore_stt_until = time.time() + seconds

    def should_ignore_stt_now(self) -> bool:
        return time.time() < self.ignore_stt_until

    def set_current_tts_text(self, text: str) -> None:
        with self.current_tts_lock:
            self.current_tts_text = normalize_text(text)

    def set_current_tts_chunk(self, text: str) -> None:
        with self.current_tts_lock:
            self.current_tts_chunk = normalize_text(text)

    def clear_current_tts_chunk(self) -> None:
        with self.current_tts_lock:
            if self.current_tts_chunk:
                self.recent_tts_chunks.append((self.current_tts_chunk, time.time()))
            self.current_tts_chunk = ""
            self._cleanup_recent_chunks_locked()

    def is_own_tts_fragment(self, text: str) -> bool:
        text = normalize_text(text)

        with self.current_tts_lock:
            if not text:
                return False

            if self.current_tts_chunk and text in self.current_tts_chunk:
                return True

            self._cleanup_recent_chunks_locked()

            for chunk, _ in self.recent_tts_chunks:
                if text in chunk:
                    return True

            return False

    def clear_tts_context(self) -> None:
        with self.current_tts_lock:
            self.current_tts_text = ""
            self.current_tts_chunk = ""
            self.recent_tts_chunks.clear()

    def _cleanup_recent_chunks_locked(self) -> None:
        now = time.time()
        self.recent_tts_chunks = [
            (chunk, ts)
            for chunk, ts in self.recent_tts_chunks
            if now - ts <= self.echo_ignore_seconds
        ]

    def recent_tts_contains_any(self, words: list[str]) -> bool:
        normalized_words = [normalize_text(word) for word in words]

        with self.current_tts_lock:
            self._cleanup_recent_chunks_locked()

            chunks = []

            if self.current_tts_chunk:
                chunks.append(self.current_tts_chunk)

            chunks.extend(chunk for chunk, _ in self.recent_tts_chunks)

            return any(
                word in chunk
                for chunk in chunks
                for word in normalized_words
                if word
            )