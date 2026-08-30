import threading

# Shared across gps.py, sensors.py, device.py. All calls to the data-bearing
# Termux:API commands (termux-location, termux-sensor, termux-battery-status)
# go through this lock -- multiple background threads (gps_watchdog,
# battery_watchdog, auto_start_watchdog, plus the main recording loop) call
# these independently, and firing several of them at the exact same instant
# (most visibly right at process startup, when all watchdog threads start
# together) was observed to make termux-location return an empty response,
# misread as "GPS dezactivat" even though location was on (see conversation
# from 2026-08-04). Serializing them trades a few seconds of extra wait on
# background checks for calls that no longer step on each other.
LOCK = threading.Lock()
