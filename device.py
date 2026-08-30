import json
import logging
import subprocess

import termux_api

logger = logging.getLogger("tractor_tracker.device")

GPS_ALERT_ID = "gps_alert"


def notify_gps_disabled():
    """Persistent, high-priority, vibrating notification -- stays on screen
    (not swipeable) until notify_gps_enabled() clears it."""
    try:
        with termux_api.LOCK:
            subprocess.run(
                [
                    "termux-notification",
                    "--id", GPS_ALERT_ID,
                    "--title", "ATENTIE ! GPS INACTIV.",
                    "--content", "REACTIVATI DETERMINAREA LOCATIEI !",
                    "--priority", "max",
                    "--vibrate", "500,200,500,200,500",
                    "--ongoing",
                ],
                capture_output=True, text=True, timeout=10,
            )
    except subprocess.TimeoutExpired:
        # Unhandled before v1.23, this crashed gps_watchdog's whole thread
        # permanently (silent -- no more GPS-disabled alerts until the next
        # process restart) the one time termux-notification hung past 10s on
        # this device (see conversation from 2026-08-06 log analysis).
        logger.warning("termux-notification nu a răspuns în 10s")


def clear_gps_alert():
    try:
        with termux_api.LOCK:
            subprocess.run(
                ["termux-notification-remove", GPS_ALERT_ID],
                capture_output=True, text=True, timeout=10,
            )
    except subprocess.TimeoutExpired:
        logger.warning("termux-notification-remove nu a răspuns în 10s")


def get_battery_status(timeout_s=10):
    """Returns the parsed `termux-battery-status` JSON (keys include
    "percentage", "status" e.g. CHARGING/DISCHARGING/FULL, "plugged" e.g.
    AC/USB/UNPLUGGED -- confirm exact field names on-device, see SETUP.md),
    or None if the call fails or the output can't be parsed."""
    try:
        with termux_api.LOCK:
            result = subprocess.run(
                ["termux-battery-status"],
                capture_output=True, text=True, timeout=timeout_s,
            )
    except subprocess.TimeoutExpired:
        logger.warning("termux-battery-status nu a răspuns în %ss", timeout_s)
        return None
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Răspuns nevalid de la termux-battery-status: %s", result.stdout)
        return None
