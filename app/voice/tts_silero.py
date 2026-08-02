import queue
import threading
import time
from typing import Callable, Optional

import numpy as np
import sounddevice as sd
import torch
from silero import silero_tts

from app.voice.audio_state import AudioState
from app.voice.text_utils import (
    clean_text,
    replace_numbers_with_words,
    split_long_text,
    transcribe_latin_for_russian_tts,
)


AudioItem = tuple[str, np.ndarray] | None


class SileroTTS:
    def __init__(
        self,
        state: AudioState,
        speaker: str = "xenia",
        model_id: str = "v5_5_ru",
        sample_rate: int = 48000,
    ) -> None:
        self.state = state
        self.speaker = speaker
        self.model_id = model_id
        self.sample_rate = sample_rate

        self.model = None
        self.audio_queue: queue.Queue[AudioItem] = queue.Queue()
        self._worker_thread: Optional[threading.Thread] = None
        self._player_thread: Optional[threading.Thread] = None

    def load(self) -> None:
        print("🔄 Загружаю Silero TTS...")
        torch.set_num_threads(4)

        self.model, _ = silero_tts(
            language="ru",
            speaker=self.model_id,
        )

        print("🔥 Прогреваю Silero...")

        _ = self.model.apply_tts(
            text="Проверка голоса.",
            speaker=self.speaker,
            sample_rate=self.sample_rate,
            put_accent=True,
            put_yo=True,
            put_stress_homo=True,
            put_yo_homo=True,
        )

        print("✅ Silero готов.")

    def speak(
        self,
        text: str,
        on_start: Optional[Callable[[], None]] = None,
        on_finish: Optional[Callable[[], None]] = None,
    ) -> None:
        if self.model is None:
            raise RuntimeError("SileroTTS.load() must be called first")

        if self.state.is_speaking.is_set():
            print("🔇 Уже говорю, новая озвучка пропущена.")
            return

        text = transcribe_latin_for_russian_tts(text)
        text = replace_numbers_with_words(text)
        self.state.set_current_tts_text(text)

        chunks = [
            cleaned
            for chunk in split_long_text(text, max_length=90)
            if (cleaned := clean_text(chunk))
        ]

        self.state.reset_tts_interrupted()
        self.state.stop_speaking.clear()
        self.state.is_speaking.set()
        self.state.ignore_regular_stt.set()

        if on_start:
            on_start()

        self._clear_audio_queue()

        self._worker_thread = threading.Thread(
            target=self._generate_audio_chunks,
            args=(chunks,),
            daemon=True,
        )
        self._player_thread = threading.Thread(
            target=self._play_audio_chunks,
            args=(on_finish,),
            daemon=True,
        )

        self._worker_thread.start()
        self._player_thread.start()

    def stop(self) -> None:
        print("🛑 Останавливаю озвучку.")
        self.state.mark_tts_interrupted()
        self.state.stop_speaking.set()

        try:
            sd.stop()
        except Exception:
            pass

        self._clear_audio_queue()

    def _generate_audio_chunks(self, chunks: list[str]) -> None:
        try:
            for chunk in chunks:
                if self.state.stop_speaking.is_set():
                    break

                try:
                    audio = self.model.apply_tts(
                        text=chunk,
                        speaker=self.speaker,
                        sample_rate=self.sample_rate,
                        put_accent=True,
                        put_yo=True,
                        put_stress_homo=True,
                        put_yo_homo=True,
                    )

                    if isinstance(audio, torch.Tensor):
                        audio = audio.detach().cpu().numpy()

                    self.audio_queue.put((chunk, audio))

                except Exception as e:
                    print(f"❌ Ошибка генерации TTS чанка: {e}")

        finally:
            self.audio_queue.put(None)

    def _play_audio_chunks(self, on_finish: Optional[Callable[[], None]]) -> None:
        try:
            while not self.state.stop_speaking.is_set():
                item = self.audio_queue.get()

                if item is None:
                    break

                chunk_text, audio = item
                self.state.set_current_tts_chunk(chunk_text)

                sd.play(audio, samplerate=self.sample_rate)

                while not self.state.stop_speaking.is_set():
                    stream = sd.get_stream()
                    if stream is None or not stream.active:
                        break
                    time.sleep(0.03)

                sd.stop()
                self.state.clear_current_tts_chunk()

        finally:
            self.state.is_speaking.clear()
            self.state.ignore_regular_stt.clear()
            self.state.stop_speaking.clear()
            self.state.clear_tts_context()
            self._clear_audio_queue()

            if on_finish:
                on_finish()

            print("✅ Озвучка завершена.")

    def _clear_audio_queue(self) -> None:
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
