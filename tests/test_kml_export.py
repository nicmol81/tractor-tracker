import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import kml_export  # noqa: E402

POINTS = [
    {"time": "2026-08-02T10:00:00+00:00", "lat": 44.4268, "lon": 26.1025, "accuracy": 8, "speed_kmh": 0.0},
    {"time": "2026-08-02T10:10:00+00:00", "lat": 44.4368, "lon": 26.1025, "accuracy": 9, "speed_kmh": 12.0},
]


class TestHaversine(unittest.TestCase):
    def test_known_distance_is_close_to_expected(self):
        # 0.01 deg latitude difference at this latitude is ~1.11 km
        d = kml_export.haversine_m(44.4268, 26.1025, 44.4368, 26.1025)
        self.assertAlmostEqual(d, 1112, delta=15)

    def test_zero_distance_for_identical_points(self):
        self.assertEqual(kml_export.haversine_m(44.0, 26.0, 44.0, 26.0), 0.0)


class TestComputeSummary(unittest.TestCase):
    def test_empty_points(self):
        summary = kml_export.compute_summary([])
        self.assertEqual(summary["distance_km"], 0.0)

    def test_distance_and_duration(self):
        summary = kml_export.compute_summary(POINTS)
        self.assertAlmostEqual(summary["distance_km"], 1.11, delta=0.05)
        self.assertEqual(summary["duration_min"], 10.0)
        self.assertGreater(summary["avg_speed_kmh"], 0)


class TestBuildAndExportKmz(unittest.TestCase):
    def test_kml_contains_coordinates(self):
        kml_str = kml_export.build_kml(POINTS, "Test")
        self.assertIn("26.1025,44.4268", kml_str)
        self.assertIn("<LineString>", kml_str)

    def test_export_kmz_is_valid_zip_with_doc_kml(self, tmp_path=Path("test_output.kmz")):
        try:
            kml_export.export_kmz(POINTS, tmp_path, "Test session")
            self.assertTrue(zipfile.is_zipfile(tmp_path))
            with zipfile.ZipFile(tmp_path) as zf:
                self.assertIn("doc.kml", zf.namelist())
        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
