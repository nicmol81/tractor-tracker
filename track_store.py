import json
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path.home() / ".tractor_tracker"
SESSION_DIR = BASE_DIR / "session"
POINTS_FILE = SESSION_DIR / "points.jsonl"
META_FILE = SESSION_DIR / "meta.json"
PENDING_DIR = BASE_DIR / "pending"
ARCHIVE_DIR = Path.home() / "storage" / "shared" / "TractorTracks"


def has_active_session():
    return META_FILE.exists()


def start_session():
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    POINTS_FILE.write_text("", encoding="utf-8")
    META_FILE.write_text(
        json.dumps({"start_time": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8",
    )


def append_point(point):
    with POINTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(point) + "\n")


def load_points():
    if not POINTS_FILE.exists():
        return []
    points = []
    with POINTS_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                points.append(json.loads(line))
    return points


def get_session_start():
    meta = json.loads(META_FILE.read_text(encoding="utf-8"))
    return datetime.fromisoformat(meta["start_time"])


def clear_session():
    for f in (POINTS_FILE, META_FILE):
        if f.exists():
            f.unlink()


def ensure_dirs():
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
