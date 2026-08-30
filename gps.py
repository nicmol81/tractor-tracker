import json
import logging
import subprocess
import time
from datetime import datetime, timezone

import termux_api

logger = logging.getLogger("tractor_tracker.gps")


def check_gps_enabled(timeout_s=8):
    # On some devices termux-location prints an error mentioning the location
    # setting when it's off; on others (confirmed on-device 2026-08-03) it
    # just returns a completely empty response in a few seconds, with no
    # error text at all. There's no dedicated status query, so both signals
    # are treated as "disabled".
    try:
        with termux_api.LOCK:
            result = subprocess.run(
                ["termux-location", "-p", "gps", "-r", "once"],
                capture_output=True, text=True, timeout=timeout_s,
            )
    except subprocess.TimeoutExpired:
        return True  # still running -- most likely just hasn't found a fix yet
    combined = (result.stdout + result.stderr).strip()
    if not combined:
        logger.warning("GPS pare oprit (termux-location nu a răspuns nimic în %ss)", timeout_s)
        return False
    if "disabled" in combined.lower() or "not enabled" in combined.lower() or "permission" in combined.lower():
        logger.warning("GPS pare oprit (răspuns termux-location: %s)", combined)
        return False
    return True


def _normalize(raw_json):
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if "accuracy" not in data or "latitude" not in data or "longitude" not in data:
        return None
    speed_ms = data.get("speed") or 0
    return {
        "time": datetime.now(timezone.utc).isoformat(),
        "lat": data["latitude"],
        "lon": data["longitude"],
        "accuracy": data["accuracy"],
        "speed_kmh": round(speed_ms * 3.6, 2),
    }


def _call_once(timeout_s):
    try:
        with termux_api.LOCK:
            result = subprocess.run(
                ["termux-location", "-p", "gps", "-r", "once"],
                capture_output=True, text=True, timeout=timeout_s,
            )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout


def get_fix_within(accuracy_m, timeout_s, poll_interval_s=5):
    """Repeatedly requests a fresh single fix (`-r once`) until one at least
    as accurate as accuracy_m arrives, or timeout_s elapses (pas2/pas2.2 in
    flow.txt).

    Deliberately NOT using `-r updates` (a continuous GPS session) here:
    Termux:API 0.53.0 has a confirmed crash (IllegalStateException in
    LocationAPI.locationToJson -- "JSON must have only one top-level value")
    when writing the *second* location update within one `-r updates`
    session, which silently cuts off further updates mid-retry (incident
    captured on-device 2026-08-03). Repeated `-r once` calls are unaffected
    since each is a self-contained request producing exactly one JSON
    response, never touching the code path that crashes."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        raw = _call_once(max(1, min(15, remaining)))
        point = _normalize(raw) if raw else None
        if point is not None and point["accuracy"] < accuracy_m:
            logger.info("Fix GPS: acc=%.1fm viteza=%.1fkm/h", point["accuracy"], point["speed_kmh"])
            return point
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_interval_s, remaining))
    logger.warning("Nu s-a obținut fix GPS sub %sm în %ss", accuracy_m, timeout_s)
    return None


def get_fix_with_retry(cfg, on_retry_message=None):
    point = get_fix_within(cfg["gps_accuracy_m"], cfg["gps_timeout_s"])
    if point is not None:
        return point
    if on_retry_message:
        on_retry_message(
            f"Nu am putut determina locația cu o precizie mai mică de "
            f"{cfg['gps_accuracy_m']}m în mai puțin de {cfg['gps_timeout_s']}s. Reîncerc."
        )
    time.sleep(30)
    return get_fix_within(cfg["gps_retry_accuracy_m"], cfg["gps_retry_timeout_s"])
