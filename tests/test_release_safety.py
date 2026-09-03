import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.modules.system.power_control_module import SystemPowerControlModule
from app.modules.system.scheduler_module import SystemSchedulerModule
from app.scheduler.reminders import ReminderWorker, ScheduledJob


class ReleasePowerSafetyTests(unittest.TestCase):
    def test_shutdown_request_never_shuts_down_without_confirmation(self):
        module = SystemPowerControlModule()
        with patch(
            "app.modules.system.power_control_module.time.monotonic",
            return_value=100.0,
        ), patch(
            "app.modules.system.power_control_module.shutdown_workstation"
        ) as shutdown:
            response = module.execute_action("power.shutdown.request", {})

        shutdown.assert_not_called()
        self.assertIn("Подтверди", response.text)
        self.assertEqual(module._pending_action, "shutdown")

    def test_shutdown_confirmation_executes_only_while_request_is_fresh(self):
        module = SystemPowerControlModule()
        with patch(
            "app.modules.system.power_control_module.time.monotonic",
            side_effect=[100.0, 101.0],
        ), patch(
            "app.modules.system.power_control_module.shutdown_workstation"
        ) as shutdown:
            module.execute_action("power.shutdown.request", {})
            response = module.execute_action("power.confirm", {})

        shutdown.assert_called_once_with()
        self.assertIn("Выключаю", response.text)
        self.assertEqual(module._pending_action, "")

    def test_expired_confirmation_cannot_execute_power_action(self):
        module = SystemPowerControlModule()
        with patch(
            "app.modules.system.power_control_module.time.monotonic",
            side_effect=[100.0, 131.0],
        ), patch(
            "app.modules.system.power_control_module.shutdown_workstation"
        ) as shutdown:
            module.execute_action("power.shutdown.request", {})
            response = module.execute_action("power.confirm", {})

        shutdown.assert_not_called()
        self.assertIn("Нет активного действия", response.text)
        self.assertEqual(module._pending_action, "")

    def test_cancel_clears_pending_power_action(self):
        module = SystemPowerControlModule()
        with patch(
            "app.modules.system.power_control_module.time.monotonic",
            return_value=100.0,
        ), patch(
            "app.modules.system.power_control_module.restart_workstation"
        ) as restart:
            module.execute_action("power.restart.request", {})
            response = module.execute_action("power.cancel", {})
            confirm = module.execute_action("power.confirm", {})

        restart.assert_not_called()
        self.assertIn("Отменила", response.text)
        self.assertIn("Нет активного действия", confirm.text)


class ReleaseSchedulerSafetyTests(unittest.TestCase):
    def _job(self) -> ScheduledJob:
        return ScheduledJob(
            job_id="job123",
            kind="reminder",
            label="проверить Ziren",
            due_at=100.0,
            created_at=50.0,
        )

    def test_successful_delivery_acknowledges_persisted_job(self):
        store = Mock()
        worker = ReminderWorker(store)
        worker._speak_when_available = Mock(return_value=True)

        with patch("app.scheduler.reminders.emit_event"), patch(
            "app.scheduler.reminders.add_log"
        ):
            worker._deliver_and_ack(self._job())

        store.remove.assert_called_once_with("job123")
        worker._speak_when_available.assert_called_once()

    def test_failed_tts_keeps_job_for_retry(self):
        store = Mock()
        worker = ReminderWorker(store)
        worker._speak_when_available = Mock(return_value=False)
        worker._stop.wait = Mock(return_value=False)

        with patch("app.scheduler.reminders.emit_event"), patch(
            "app.scheduler.reminders.add_log"
        ):
            worker._deliver_and_ack(self._job())

        store.remove.assert_not_called()
        self.assertNotIn("job123", worker._inflight)

    def test_delivery_exception_does_not_acknowledge_job(self):
        store = Mock()
        worker = ReminderWorker(store)
        worker._stop.wait = Mock(return_value=False)

        with patch(
            "app.scheduler.reminders.emit_event",
            side_effect=RuntimeError("event bus unavailable"),
        ), patch("app.scheduler.reminders.add_log"):
            worker._deliver_and_ack(self._job())

        store.remove.assert_not_called()
        self.assertNotIn("job123", worker._inflight)

    def test_scheduler_understands_composed_russian_numbers(self):
        module = SystemSchedulerModule(store=Mock(), start_worker=False)
        action_id, arguments = module._parse_local(
            "напомни через двадцать пять минут проверить релиз"
        )
        self.assertEqual(action_id, "scheduler.reminder.relative")
        self.assertEqual(arguments["minutes"], 25)
        self.assertEqual(arguments["label"], "проверить релиз")

    def test_scheduler_understands_spoken_clock_time(self):
        module = SystemSchedulerModule(store=Mock(), start_worker=False)
        action_id, arguments = module._parse_local(
            "поставь будильник на семь тридцать тест"
        )
        self.assertEqual(action_id, "scheduler.alarm.clock")
        self.assertEqual(arguments["time"], "07:30")
        self.assertEqual(arguments["label"], "тест")


if __name__ == "__main__":
    unittest.main()
