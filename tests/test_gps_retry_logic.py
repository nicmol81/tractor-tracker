import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gps  # noqa: E402

GOOD_FIX = json.dumps({"latitude": 44.4, "longitude": 26.1, "accuracy": 8, "speed": 2.0})
POOR_FIX = json.dumps({"latitude": 44.4, "longitude": 26.1, "accuracy": 50, "speed": 2.0})


class TestGetFixWithin(unittest.TestCase):
    @patch("gps._call_once")
    def test_returns_point_when_accurate_enough(self, mock_call):
        mock_call.return_value = GOOD_FIX
        point = gps.get_fix_within(accuracy_m=20, timeout_s=5)
        self.assertIsNotNone(point)
        self.assertEqual(point["lat"], 44.4)
        self.assertLess(point["accuracy"], 20)

    @patch("gps._call_once")
    def test_returns_none_when_never_accurate_within_timeout(self, mock_call):
        mock_call.return_value = POOR_FIX
        point = gps.get_fix_within(accuracy_m=20, timeout_s=0.3, poll_interval_s=0.05)
        self.assertIsNone(point)

    @patch("gps._call_once")
    def test_returns_none_on_malformed_output(self, mock_call):
        mock_call.return_value = "not json"
        point = gps.get_fix_within(accuracy_m=20, timeout_s=0.2, poll_interval_s=0.05)
        self.assertIsNone(point)

    @patch("gps._call_once")
    def test_returns_none_when_call_produces_nothing(self, mock_call):
        mock_call.return_value = None
        point = gps.get_fix_within(accuracy_m=20, timeout_s=0.2, poll_interval_s=0.05)
        self.assertIsNone(point)

    @patch("gps._call_once")
    def test_retries_across_multiple_calls_until_accurate(self, mock_call):
        mock_call.side_effect = [POOR_FIX, POOR_FIX, GOOD_FIX]
        point = gps.get_fix_within(accuracy_m=20, timeout_s=5, poll_interval_s=0.01)
        self.assertIsNotNone(point)
        self.assertLess(point["accuracy"], 20)
        self.assertEqual(mock_call.call_count, 3)


class TestCheckGpsEnabled(unittest.TestCase):
    @patch("gps.subprocess.run")
    def test_empty_response_means_disabled(self, mock_run):
        # Confirmed on-device 2026-08-03: with Location off, termux-location
        # returns completely empty stdout/stderr within a few seconds --
        # no error text at all.
        mock_run.return_value = MagicMock(stdout="", stderr="", returncode=0)
        self.assertFalse(gps.check_gps_enabled())

    @patch("gps.subprocess.run")
    def test_valid_location_json_means_enabled(self, mock_run):
        mock_run.return_value = MagicMock(stdout=GOOD_FIX, stderr="", returncode=0)
        self.assertTrue(gps.check_gps_enabled())

    @patch("gps.subprocess.run")
    def test_explicit_disabled_text_means_disabled(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="", stderr="location is disabled", returncode=1,
        )
        self.assertFalse(gps.check_gps_enabled())

    @patch("gps.subprocess.run")
    def test_process_still_running_assumes_enabled(self, mock_run):
        mock_run.side_effect = gps.subprocess.TimeoutExpired(cmd="termux-location", timeout=8)
        self.assertTrue(gps.check_gps_enabled())


class TestGetFixWithRetry(unittest.TestCase):
    @patch("gps.time.sleep")
    @patch("gps.get_fix_within")
    def test_retries_with_looser_thresholds_and_notifies(self, mock_get_fix, mock_sleep):
        good_point = {"lat": 44.4, "lon": 26.1, "accuracy": 25, "speed_kmh": 0}
        mock_get_fix.side_effect = [None, good_point]
        messages = []

        cfg = {"gps_accuracy_m": 20, "gps_timeout_s": 40,
               "gps_retry_accuracy_m": 30, "gps_retry_timeout_s": 60}
        result = gps.get_fix_with_retry(cfg, on_retry_message=messages.append)

        self.assertEqual(result, good_point)
        self.assertEqual(len(messages), 1)
        self.assertIn("Reîncerc", messages[0])
        mock_sleep.assert_called_once_with(30)
        first_call_args = mock_get_fix.call_args_list[0].args
        second_call_args = mock_get_fix.call_args_list[1].args
        self.assertEqual(first_call_args, (20, 40))
        self.assertEqual(second_call_args, (30, 60))

    @patch("gps.time.sleep")
    @patch("gps.get_fix_within")
    def test_returns_none_when_both_attempts_fail(self, mock_get_fix, mock_sleep):
        mock_get_fix.side_effect = [None, None]
        cfg = {"gps_accuracy_m": 20, "gps_timeout_s": 40,
               "gps_retry_accuracy_m": 30, "gps_retry_timeout_s": 60}
        result = gps.get_fix_with_retry(cfg)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
