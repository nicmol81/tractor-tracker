import json
import logging
import math
import subprocess

import termux_api

logger = logging.getLogger("tractor_tracker.sensors")


def _parse_xyz_samples(raw_text):
    """`termux-sensor -n N` emits N separate top-level JSON objects
    concatenated together -- NOT one JSON object with an array of N samples
    -- each shaped like {"<sensor name>": {"values": [x, y, z]}}, e.g.
    {"LSM6DSOTR Accelerometer": {"values": [0.47, 0.49, 9.83]}} (confirmed
    on-device 2026-08-04). A plain json.loads() on the whole output fails
    silently ("extra data") since it's not a single JSON document."""
    decoder = json.JSONDecoder()
    text = raw_text.strip()
    samples = []
    while text:
        try:
            obj, idx = decoder.raw_decode(text)
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict):
            for key, value in obj.items():
                if "accel" in key.lower() and isinstance(value, dict):
                    values = value.get("values")
                    if values and len(values) >= 3:
                        samples.append(values[:3])
        text = text[idx:].lstrip()
    return samples


def _sample_accelerometer(n=5, delay_ms=200, timeout_s=10):
    try:
        with termux_api.LOCK:
            result = subprocess.run(
                ["termux-sensor", "-s", "accelerometer", "-n", str(n), "-d", str(delay_ms)],
                capture_output=True, text=True, timeout=timeout_s,
            )
    except subprocess.TimeoutExpired:
        logger.warning("termux-sensor nu a răspuns în %ss", timeout_s)
        return []
    if result.returncode != 0:
        logger.warning("termux-sensor a eșuat (cod %s): %s", result.returncode, result.stderr.strip())
        return []
    samples = _parse_xyz_samples(result.stdout)
    if not samples:
        logger.warning("Nu am putut extrage eșantioane accelerometru din răspuns: %s",
                        result.stdout[:200].replace("\n", " "))
    return samples


def is_motion_detected(threshold):
    """True if accelerometer magnitude varies beyond `threshold` across a short
    burst of samples, meaning the tractor likely started moving again."""
    xyz_samples = _sample_accelerometer()
    magnitudes = [math.sqrt(x * x + y * y + z * z) for x, y, z in xyz_samples]
    if len(magnitudes) < 2:
        return False
    mean = sum(magnitudes) / len(magnitudes)
    variance = sum((m - mean) ** 2 for m in magnitudes) / len(magnitudes)
    motion = variance > threshold
    # Logged at INFO regardless of outcome (not just positive detections) so
    # the full history is visible in /getlogfile -- needed to calibrate
    # accel_motion_threshold and the auto-start window/ratio from real
    # driving data instead of guessing (see conversation from 2026-08-04).
    logger.info("Accelerometru: varianță=%.5f prag=%.3f -> %s",
                variance, threshold, "mișcare" if motion else "staționar")
    return motion
