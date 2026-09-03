import copy
import unittest
from unittest.mock import Mock

from app.modules.system.scheduler_module import SystemSchedulerModule
from app.settings.trigger_store import TriggerStore


class SchedulerCustomTriggerReleaseTests(unittest.TestCase):
    @staticmethod
    def _module_with_custom_trigger(action_id: str, trigger: str) -> SystemSchedulerModule:
        module = SystemSchedulerModule(store=Mock(), start_worker=False)
        trigger_store = Mock(spec=TriggerStore)

        def get_groups(_feature_id, defaults):
            groups = copy.deepcopy(defaults)
            groups[action_id]["triggers"] = [trigger]
            return groups

        trigger_store.get_groups.side_effect = get_groups
        module.set_trigger_store(trigger_store)
        return module

    def test_custom_reminder_prefix_is_used_by_snake_parser(self):
        module = self._module_with_custom_trigger(
            "scheduler.reminder.relative",
            "напомни мне",
        )
        parsed = module._parse_local(
            "напомни мне через двадцать минут проверить сборку"
        )

        self.assertIsNotNone(parsed)
        action_id, arguments = parsed
        self.assertEqual(action_id, "scheduler.reminder.relative")
        self.assertEqual(arguments["minutes"], 20)
        self.assertEqual(arguments["label"], "проверить сборку")

    def test_custom_relative_alarm_prefix_accepts_optional_through_word(self):
        module = self._module_with_custom_trigger(
            "scheduler.alarm.relative",
            "разбуди меня",
        )
        parsed = module._parse_local("разбуди меня через два часа")

        self.assertIsNotNone(parsed)
        action_id, arguments = parsed
        self.assertEqual(action_id, "scheduler.alarm.relative")
        self.assertEqual(arguments["hours"], 2)

    def test_custom_clock_alarm_prefix_accepts_optional_on_word(self):
        module = self._module_with_custom_trigger(
            "scheduler.alarm.clock",
            "разбуди утром",
        )
        parsed = module._parse_local("разбуди утром на семь тридцать тренировка")

        self.assertIsNotNone(parsed)
        action_id, arguments = parsed
        self.assertEqual(action_id, "scheduler.alarm.clock")
        self.assertEqual(arguments["time"], "07:30")
        self.assertEqual(arguments["label"], "тренировка")

    def test_matched_custom_trigger_without_arguments_stays_in_local_route(self):
        module = self._module_with_custom_trigger(
            "scheduler.reminder.relative",
            "напомни мне",
        )
        parsed = module._parse_local("напомни мне")

        self.assertEqual(parsed, ("scheduler.reminder.relative", {}))
        self.assertTrue(module.can_handle("напомни мне"))


if __name__ == "__main__":
    unittest.main()
