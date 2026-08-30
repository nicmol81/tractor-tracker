import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import track_store  # noqa: E402


class TestTrackStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        track_store.SESSION_DIR = base / "session"
        track_store.POINTS_FILE = track_store.SESSION_DIR / "points.jsonl"
        track_store.META_FILE = track_store.SESSION_DIR / "meta.json"
        track_store.PENDING_DIR = base / "pending"
        track_store.ARCHIVE_DIR = base / "archive"

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_active_session_initially(self):
        self.assertFalse(track_store.has_active_session())

    def test_start_creates_session_with_no_points(self):
        track_store.start_session()
        self.assertTrue(track_store.has_active_session())
        self.assertEqual(track_store.load_points(), [])

    def test_append_and_load_points_round_trip(self):
        track_store.start_session()
        point = {"time": datetime.now(timezone.utc).isoformat(), "lat": 44.0, "lon": 26.0,
                  "accuracy": 10, "speed_kmh": 5.0}
        track_store.append_point(point)
        track_store.append_point(point)
        points = track_store.load_points()
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0]["lat"], 44.0)

    def test_get_session_start_matches_recorded_time(self):
        before = datetime.now(timezone.utc)
        track_store.start_session()
        start = track_store.get_session_start()
        self.assertGreaterEqual(start, before)

    def test_clear_session_removes_files(self):
        track_store.start_session()
        track_store.append_point({"time": "x", "lat": 0, "lon": 0, "accuracy": 1, "speed_kmh": 0})
        track_store.clear_session()
        self.assertFalse(track_store.has_active_session())
        self.assertEqual(track_store.load_points(), [])

    def test_ensure_dirs_creates_pending_and_archive(self):
        track_store.ensure_dirs()
        self.assertTrue(track_store.PENDING_DIR.is_dir())
        self.assertTrue(track_store.ARCHIVE_DIR.is_dir())


if __name__ == "__main__":
    unittest.main()
