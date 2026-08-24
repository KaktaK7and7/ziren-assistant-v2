import copy
import unittest
from unittest.mock import Mock, patch

from app.scheduler.reminders import ReminderStore, ReminderWorker, ScheduledJob


class SchedulerRestartReleaseTests(unittest.TestCase):
    def test_alarm_persists_across_new_store_instance(self):
        state = {"data": []}

        def fake_read(_path, default=None):
            return copy.deepcopy(state["data"])

        def fake_write(_path, payload):
            state["data"] = copy.deepcopy(payload)

        with (
            patch("app.scheduler.reminders.read_json", side_effect=fake_read),
            patch("app.scheduler.reminders.write_json", side_effect=fake_write),
            patch("app.scheduler.reminders.time.time", return_value=100.0),
        ):
            first_store = ReminderStore()
            created = first_store.add("alarm", "Подъём", 200.0)

            # A fresh instance models Core being restarted and rebuilding the
            # scheduler from the same persisted JSON storage.
            restarted_store = ReminderStore()
            restored = restarted_store.list_jobs()

        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0].job_id, created.job_id)
        self.assertEqual(restored[0].kind, "alarm")
        self.assertEqual(restored[0].label, "Подъём")
        self.assertEqual(restored[0].due_at, 200.0)

    def test_removed_inflight_alarm_is_cancelled_before_beep(self):
        store = Mock()
        store.has_job.side_effect = [True, False]
        worker = ReminderWorker(store)
        job = ScheduledJob(
            job_id="alarm-1",
            kind="alarm",
            label="Подъём",
            due_at=1.0,
            created_at=0.0,
        )

        with (
            patch.object(worker, "_beep_alarm") as beep,
            patch.object(worker, "_speak_when_available") as speak,
            patch("app.scheduler.reminders.emit_event"),
        ):
            worker._deliver_and_ack(job)

        beep.assert_not_called()
        speak.assert_not_called()
        store.remove.assert_not_called()

    def test_removed_job_while_waiting_for_tts_is_not_acknowledged(self):
        store = Mock()
        # delivery preflight -> after event -> speak-loop cancellation
        store.has_job.side_effect = [True, True, False]
        worker = ReminderWorker(store)
        job = ScheduledJob(
            job_id="reminder-1",
            kind="reminder",
            label="Проверить сборку",
            due_at=1.0,
            created_at=0.0,
        )

        with patch("app.scheduler.reminders.emit_event"):
            worker._deliver_and_ack(job)

        store.remove.assert_not_called()


if __name__ == "__main__":
    unittest.main()
