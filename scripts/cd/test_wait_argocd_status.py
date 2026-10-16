#!/usr/bin/env python3
"""Prove SSM visibility retries are narrow and terminal failures stay failures."""

import importlib.util
import unittest
from pathlib import Path

PATH = Path(__file__).with_name("wait-argocd-status.py")
SPEC = importlib.util.spec_from_file_location("wait_argocd_status", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeClock:
    def __init__(self):
        self.now = 0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class WaitStatusTests(unittest.TestCase):
    def test_retries_eventual_visibility_then_pending_until_success(self):
        clock = FakeClock()
        events = iter([
            RuntimeError("InvocationDoesNotExist"),
            {"Status": "Pending"},
            {"Status": "Success", "StandardOutputContent": '{"status":"Healthy","smoke":"Succeeded"}'},
        ])

        def get(*_args):
            item = next(events)
            if isinstance(item, Exception):
                raise item
            return item

        result = MODULE.wait_for_command("cmd", "i-abc", 30, get, clock.sleep, clock.monotonic)
        self.assertEqual(result["status"], "Healthy")
        self.assertEqual(clock.now, 10)

    def test_fails_immediately_for_permission_error(self):
        clock = FakeClock()

        def get(*_args):
            raise RuntimeError("AccessDeniedException")

        with self.assertRaisesRegex(RuntimeError, "AccessDenied"):
            MODULE.wait_for_command("cmd", "i-abc", 30, get, clock.sleep, clock.monotonic)
        self.assertEqual(clock.now, 0)

    def test_terminal_status_and_bad_summary_fail(self):
        for result, message in [
            ({"Status": "Failed"}, "Failed"),
            ({"Status": "Success", "StandardOutputContent": "not-json"}, "valid summary"),
            ({"Status": "Success", "StandardOutputContent": '{"status":"Healthy","smoke":"Failed"}'}, "smoke success"),
        ]:
            with self.subTest(result=result):
                with self.assertRaisesRegex(RuntimeError, message):
                    MODULE.wait_for_command("cmd", "i-abc", 30, lambda *_args: result, lambda _s: None, lambda: 0)

    def test_bounds_polling_deadline(self):
        clock = FakeClock()
        with self.assertRaisesRegex(TimeoutError, "deadline"):
            MODULE.wait_for_command("cmd", "i-abc", 7, lambda *_args: {"Status": "Delayed"}, clock.sleep, clock.monotonic)
        self.assertEqual(clock.now, 7)


if __name__ == "__main__":
    unittest.main()
