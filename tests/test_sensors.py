import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sensors  # noqa: E402

# Real termux-sensor -n 5 -d 200 output captured on-device 2026-08-04 with the
# phone motionless on a table -- confirms termux-sensor emits multiple
# concatenated top-level JSON objects, not one JSON with an array inside.
REAL_STATIONARY_OUTPUT = """
{
  "LSM6DSOTR Accelerometer": {
    "values": [
      0.4764461517333984,
      0.4884171485900879,
      9.832986831665039
    ]
  }
}
{
  "LSM6DSOTR Accelerometer": {
    "values": [
      0.49559974670410156,
      0.4836287498474121,
      9.825803756713867
    ]
  }
}
{
  "LSM6DSOTR Accelerometer": {
    "values": [
      0.4836287498474121,
      0.5027823448181152,
      9.821015357971191
    ]
  }
}
{
  "LSM6DSOTR Accelerometer": {
    "values": [
      0.47165772318840027,
      0.47884035110473633,
      9.813833236694336
    ]
  }
}
{
  "LSM6DSOTR Accelerometer": {
    "values": [
      0.4908113479614258,
      0.4908113479614258,
      9.825803756713867
    ]
  }
}
"""


class TestParseXyzSamples(unittest.TestCase):
    def test_parses_all_concatenated_objects_from_real_capture(self):
        samples = sensors._parse_xyz_samples(REAL_STATIONARY_OUTPUT)
        self.assertEqual(len(samples), 5)
        self.assertAlmostEqual(samples[0][2], 9.832986831665039)

    def test_returns_empty_list_for_malformed_output(self):
        self.assertEqual(sensors._parse_xyz_samples("not json"), [])

    def test_ignores_non_accelerometer_keys(self):
        text = '{"SomeOtherSensor": {"values": [1, 2, 3]}}'
        self.assertEqual(sensors._parse_xyz_samples(text), [])


class TestIsMotionDetected(unittest.TestCase):
    @patch("sensors._sample_accelerometer")
    def test_stationary_phone_has_near_zero_variance_below_threshold(self, mock_sample):
        # Using the real captured samples: a phone resting on a table
        # produces variance around 0.00004 -- comfortably under the default
        # threshold of 1.5.
        mock_sample.return_value = sensors._parse_xyz_samples(REAL_STATIONARY_OUTPUT)
        self.assertFalse(sensors.is_motion_detected(threshold=1.5))

    @patch("sensors._sample_accelerometer")
    def test_high_variance_samples_detected_as_motion(self, mock_sample):
        mock_sample.return_value = [
            (0.5, 0.5, 9.8), (5.0, -3.0, 15.0), (0.2, 8.0, 4.0), (12.0, 0.5, 9.8), (0.5, 0.5, 2.0),
        ]
        self.assertTrue(sensors.is_motion_detected(threshold=1.5))

    @patch("sensors._sample_accelerometer")
    def test_too_few_samples_means_no_motion(self, mock_sample):
        mock_sample.return_value = [(0.5, 0.5, 9.8)]
        self.assertFalse(sensors.is_motion_detected(threshold=1.5))


if __name__ == "__main__":
    unittest.main()
