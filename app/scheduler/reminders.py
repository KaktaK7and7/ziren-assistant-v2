from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.core.log_bus import add_log
from app.events.event_bus import emit_event
from app.storage.local_store import APP_DIR, read_json, write_json
from app.voice.runtime import get_tts


SCHEDULE_FILE = APP_DIR / "scheduled_jobs.json"
MAX_JOBS = 100
TTS_WAIT_TIMEOUT_SECONDS = 90.0
TTS_RETRY_SECONDS = 0.35
DELIVERY_RETRY_SECONDS = 10.0


@dataclass(frozen=True)
class ScheduledJob:
    job_id: str
    kind: str
    label: str
    due_at: float
    created_at: float


class ReminderStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def list_jobs(self) -> list[ScheduledJob]:
        with self._lock:
            return self._read_jobs()

    def due_jobs(self, now: float | None = None) -> list[ScheduledJob]:
        current = float(now if now is not None else time.time())
        with self._lock:
            return [job for job in self._read_jobs() if job.due_at <= current]

    def add(self, kind: str, label: str, due_at: float) -> ScheduledJob:
        clean_kind = kind if kind in {"reminder", "alarm"} else "reminder"
        clean_label = " ".join(str(label or "").split())[:500]
        if not clean_label:
            clean_label = "Будильник" if clean_kind == "alarm" else "Напоминание"
        now = time.time()
        if due_at <= now:
            raise ValueError("Время должно быть в будущем")

        with self._lock:
            jobs = self._read_jobs()
            jobs = [job for job in jobs if job.due_at > now - 3600]
            if len(jobs) >= MAX_JOBS:
                raise ValueError("Слишком много активных напоминаний")
            job = ScheduledJob(
                job_id=uuid.uuid4().hex[:12],
                kind=clean_kind,
                label=clean_label,
                due_at=float(due_at),
                created_at=now,
            )
            jobs.append(job)
            self._write_jobs(jobs)
            return job

    def remove(self, job_id: str) -> bool:
        target = str(job_id or "")
        if not target:
            return False
        with self._lock:
            jobs = self._read_jobs()
            remaining = [job for job in jobs if job.job_id != target]
            if len(remaining) == len(jobs):
                return False
            self._write_jobs(remaining)
            return True

    def pop_due(self, now: float | None = None) -> list[ScheduledJob]:
        """Compatibility helper for callers that explicitly want destructive pop.

        ReminderWorker deliberately does not use this method: it keeps a due job
        persisted until the delivery path acknowledges it.
        """
        due = self.due_jobs(now)
        for job in due:
            self.remove(job.job_id)
        return due

    def clear(self) -> int:
        with self._lock:
            jobs = self._read_jobs()
            self._write_jobs([])
            return len(jobs)

    def _read_jobs(self) -> list[ScheduledJob]:
        raw = read_json(SCHEDULE_FILE, default=[])
        if not isinstance(raw, list):
            return []
        result: list[ScheduledJob] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                job = ScheduledJob(
                    job_id=str(item.get("job_id") or "")[:32],
                    kind=str(item.get("kind") or "reminder"),
                    label=str(item.get("label") or "")[:500],
                    due_at=float(item.get("due_at")),
                    created_at=float(item.get("created_at") or 0),
                )
            except (TypeError, ValueError):
                continue
            if job.job_id and job.kind in {"reminder", "alarm"}:
                result.append(job)
        return sorted(result, key=lambda job: job.due_at)[:MAX_JOBS]

    def _write_jobs(self, jobs: list[ScheduledJob]) -> None:
        write_json(
            SCHEDULE_FILE,
            [
                {
                    "job_id": job.job_id,
                    "kind": job.kind,
                    "label": job.label,
                    "due_at": job.due_at,
                    "created_at": job.created_at,
                }
                for job in jobs[:MAX_JOBS]
            ],
        )


class ReminderWorker:
    def __init__(self, store: ReminderStore) -> None:
        self.store = store
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._inflight_lock = threading.Lock()
        self._inflight: set[str] = set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="ziren-reminder-worker",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(1.0):
            for job in self.store.due_jobs():
                if not self._claim(job.job_id):
                    continue
                threading.Thread(
                    target=self._deliver_and_ack,
                    args=(job,),
                    daemon=True,
                    name=f"ziren-scheduler-delivery-{job.job_id}",
                ).start()

    def _claim(self, job_id: str) -> bool:
        with self._inflight_lock:
            if job_id in self._inflight:
                return False
            self._inflight.add(job_id)
            return True

    def _release(self, job_id: str) -> None:
        with self._inflight_lock:
            self._inflight.discard(job_id)

    def _deliver_and_ack(self, job: ScheduledJob) -> None:
        try:
            message = (
                f"Будильник. {job.label}"
                if job.kind == "alarm"
                else f"Напоминаю: {job.label}"
            )
            add_log(
                "scheduler.job.due",
                meta={"job_id": job.job_id, "kind": job.kind, "label": job.label},
            )
            emit_event(
                "scheduler.job.due",
                {
                    "job_id": job.job_id,
                    "kind": job.kind,
                    "label": job.label,
                    "message": message,
                },
            )

            if job.kind == "alarm":
                self._beep_alarm()

            if self._speak_when_available(message, job.job_id):
                self.store.remove(job.job_id)
                add_log(
                    "scheduler.job.delivered",
                    meta={"job_id": job.job_id, "kind": job.kind},
                )
                return

            add_log(
                "scheduler.job.retry_scheduled",
                level="warn",
                meta={"job_id": job.job_id, "kind": job.kind},
            )
            self._stop.wait(DELIVERY_RETRY_SECONDS)
        except Exception as error:
            # Do not acknowledge a job when any delivery stage unexpectedly
            # fails. It remains persisted and will be retried later.
            add_log(
                "scheduler.delivery.failed",
                level="warn",
                meta={"job_id": job.job_id, "error": str(error)},
            )
            self._stop.wait(DELIVERY_RETRY_SECONDS)
        finally:
            self._release(job.job_id)

    def _speak_when_available(self, message: str, job_id: str) -> bool:
        deadline = time.monotonic() + TTS_WAIT_TIMEOUT_SECONDS

        while not self._stop.is_set() and time.monotonic() < deadline:
            tts = get_tts()
            if tts is None:
                self._stop.wait(TTS_RETRY_SECONDS)
                continue

            try:
                state = getattr(tts, "state", None)
                speaking_event = getattr(state, "is_speaking", None)
                is_speaking = bool(
                    speaking_event is not None
                    and callable(getattr(speaking_event, "is_set", None))
                    and speaking_event.is_set()
                )
                if is_speaking:
                    self._stop.wait(TTS_RETRY_SECONDS)
                    continue

                tts.speak(message)
                return True
            except Exception as error:
                add_log(
                    "scheduler.tts.failed",
                    level="warn",
                    meta={"job_id": job_id, "error": str(error)},
                )
                return False

        add_log(
            "scheduler.tts.timeout",
            level="warn",
            meta={"job_id": job_id},
        )
        return False

    @staticmethod
    def _beep_alarm() -> None:
        try:
            import winsound

            winsound.Beep(1000, 700)
            winsound.Beep(1200, 700)
        except Exception:
            pass


def due_after(minutes: float = 0, hours: float = 0) -> float:
    seconds = max(0.0, float(minutes) * 60.0 + float(hours) * 3600.0)
    if seconds < 1.0:
        raise ValueError("Слишком маленький интервал")
    return time.time() + seconds


def next_clock_time(hour: int, minute: int) -> float:
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Некорректное время")
    now = datetime.now()
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate.timestamp()


def human_due_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%H:%M")
