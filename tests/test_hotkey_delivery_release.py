import unittest
from unittest.mock import call, patch

from app.pc_control import windows_input


class HotkeyDeliveryReleaseTests(unittest.TestCase):
    def test_hotkey_releases_keys_and_waits_for_shell_settle(self):
        with (
            patch("app.pc_control.windows_input._send_vk") as send_vk,
            patch("app.pc_control.windows_input.time.sleep") as sleep,
        ):
            windows_input.send_hotkey(["ctrl", "win", "left"])

        ctrl = windows_input.VK["ctrl"]
        win = windows_input.VK["win"]
        left = windows_input.VK["left"]
        self.assertEqual(
            send_vk.call_args_list,
            [
                call(ctrl),
                call(win),
                call(left),
                call(left, key_up=True),
                call(win, key_up=True),
                call(ctrl, key_up=True),
            ],
        )
        self.assertEqual(sleep.call_args_list[-1], call(windows_input.HOTKEY_SETTLE_SECONDS))


if __name__ == "__main__":
    unittest.main()
