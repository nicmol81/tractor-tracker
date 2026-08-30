import fcntl
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import device
import gps
import kml_export
import sensors
import track_store
from telegram_bot import TelegramBot
from version import VERSION

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
RUNTIME_CONFIG_PATH = BASE_DIR / "runtime_config.json"
RUNTIME_CONFIG_EXAMPLE_PATH = BASE_DIR / "runtime_config.example.json"
LOG_PATH = BASE_DIR / "tractor_tracker.log"
PID_FILE_PATH = BASE_DIR / "tractor_tracker.pid"

_formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
_file_handler = RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
_file_handler.setFormatter(_formatter)
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)
logging.basicConfig(level=logging.INFO, handlers=[_file_handler, _console_handler])
logger = logging.getLogger("tractor_tracker.main")


def load_config():
    if not CONFIG_PATH.exists():
        print("Lipsește config.json — copiază config.example.json și completează "
              "bot_token / allowed_chat_id (vezi SETUP.md).")
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def load_runtime_config():
    """runtime_config.json is the user's live, persisted settings file --
    unlike the rest of the code it must survive `unzip -o` updates untouched
    (that's what runtime_config.example.json ships for). On first run it's
    created from the bundled example; on later runs any new keys introduced
    by a code update are merged in without touching values the user already
    customized (via /rename, /set_*, or manual edits)."""
    defaults = json.loads(RUNTIME_CONFIG_EXAMPLE_PATH.read_text(encoding="utf-8"))
    if not RUNTIME_CONFIG_PATH.exists():
        save_runtime_config(defaults)
        return defaults
    cfg = json.loads(RUNTIME_CONFIG_PATH.read_text(encoding="utf-8"))
    missing = {k: v for k, v in defaults.items() if k not in cfg}
    if missing:
        logger.info("Adaug în runtime_config.json cheile noi: %s", ", ".join(missing))
        cfg.update(missing)
        save_runtime_config(cfg)
    return cfg


def save_runtime_config(cfg):
    RUNTIME_CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def acquire_single_instance_lock():
    """Grabs an exclusive flock on tractor_tracker.pid. The lock is held for
    as long as this process is alive and released automatically by the OS on
    exit (including crashes/kill -9), so there's no stale-lock cleanup to
    worry about. Prevents the confusion of the autostart supervisor's
    instance and a manually-started one both running at once."""
    global _pid_lock_fd
    _pid_lock_fd = open(PID_FILE_PATH, "w")
    try:
        fcntl.flock(_pid_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        _pid_lock_fd.close()
        return False
    _pid_lock_fd.write(str(os.getpid()))
    _pid_lock_fd.flush()
    return True


_pid_lock_fd = None


def telegram_listener(bot, command_queue, stop_event):
    while not stop_event.is_set():
        try:
            for chat_id, cmd, args in bot.poll_commands(timeout_s=25):
                logger.info("Comandă primită de la chat %s: %s %s", chat_id, cmd, args)
                command_queue.put((chat_id, cmd, args))
        except Exception:
            # Orice fir de fundal trebuie să supraviețuiască unei erori
            # neprevăzute (retea, Termux:API etc.) -- altfel piere silențios
            # și nimic nu-l mai repornește până la restart de proces (vezi
            # device.clear_gps_alert, care exact așa a omorât gps_watchdog
            # neobservat timp de zile, până la analiza jurnalului din
            # 2026-08-06). Logăm complet și continuăm bucla, nu o lăsăm să moară.
            logger.exception("Eroare neașteptată în telegram_listener, reiau după o pauză")
            stop_event.wait(5)


GPS_ALERT_TEXT = "ATENTIE ! GPS INACTIV. REACTIVATI DETERMINAREA LOCATIEI !"


def handle_gps_status(enabled, bot, gps_alert, cfg):
    """Reacts to GPS on/off transitions from wherever they're detected (the
    background watchdog or the /start_rec pas1 gate), so only one Telegram
    message and one phone notification go out per actual transition."""
    now = time.monotonic()
    if not enabled:
        if not gps_alert["active"]:
            gps_alert["active"] = True
            gps_alert["last_reminder"] = now
            logger.warning("GPS dezactivat — trimit avertizare")
            bot.send_message(GPS_ALERT_TEXT)
            device.notify_gps_disabled()
        elif (now - gps_alert["last_reminder"]) >= cfg["gps_alert_repeat_min"] * 60:
            gps_alert["last_reminder"] = now
            bot.send_message(GPS_ALERT_TEXT + " (memento)")
    else:
        if gps_alert["active"]:
            gps_alert["active"] = False
            logger.info("GPS reactivat")
            bot.send_message("Locația GPS a fost reactivată.")
            device.clear_gps_alert()


def gps_watchdog(bot, cfg, gps_alert, stop_event):
    # Staggered so this doesn't fire its first check in the exact same
    # instant as battery_watchdog/auto_start_watchdog at process startup --
    # see termux_api.LOCK for why concurrent Termux:API calls are risky.
    if stop_event.wait(5):
        return
    while not stop_event.is_set():
        try:
            enabled = gps.check_gps_enabled()
            logger.info("Verificare periodică GPS (watchdog la %ss): %s",
                        cfg["gps_check_interval_s"], "activ" if enabled else "oprit")
            handle_gps_status(enabled, bot, gps_alert, cfg)
        except Exception:
            logger.exception("Eroare neașteptată în gps_watchdog, continui")
        stop_event.wait(cfg["gps_check_interval_s"])


def format_battery_message(status):
    if status is None or status.get("percentage") is None:
        return "Nu am putut citi starea bateriei."
    pct = status["percentage"]
    plugged = status.get("plugged", "UNPLUGGED")
    charging = plugged != "UNPLUGGED"
    return f"Baterie: {pct}% ({'se încarcă' if charging else 'pe baterie'})"


def handle_battery_status(status, bot, battery_alert, cfg):
    if status is None or status.get("percentage") is None:
        return
    pct = status["percentage"]
    threshold = cfg["battery_low_threshold_pct"]
    now = time.monotonic()
    if pct < threshold:
        if not battery_alert["active"]:
            battery_alert["active"] = True
            battery_alert["last_reminder"] = now
            logger.warning("Baterie scăzută: %s%%", pct)
            bot.send_message(f"LOW BATTERY — baterie telefon din tractor: {pct}%")
        elif (now - battery_alert["last_reminder"]) >= cfg["battery_alert_repeat_min"] * 60:
            battery_alert["last_reminder"] = now
            bot.send_message(f"LOW BATTERY (memento) — baterie telefon din tractor: {pct}%")
    else:
        if battery_alert["active"]:
            battery_alert["active"] = False
            logger.info("Baterie peste prag din nou: %s%%", pct)
            bot.send_message(f"Baterie peste {threshold}% din nou: {pct}%.")


def battery_watchdog(bot, cfg, battery_alert, stop_event):
    if stop_event.wait(10):
        return
    while not stop_event.is_set():
        try:
            handle_battery_status(device.get_battery_status(), bot, battery_alert, cfg)
        except Exception:
            logger.exception("Eroare neașteptată în battery_watchdog, continui")
        stop_event.wait(cfg["battery_check_interval_s"])


def build_description(cfg):
    return (
        f"Tractor Tracker v{VERSION} — cum funcționează:\n\n"
        f"1. /start_rec pornește înregistrarea: verifică GPS-ul (dacă e oprit, avertizează pe Telegram + "
        f"notificare pe telefon și așteaptă reactivarea), apoi determină prima poziție "
        f"(prag {cfg['gps_accuracy_m']}m/{cfg['gps_timeout_s']}s; dacă eșuează, reîncearcă cu prag mai relaxat "
        f"{cfg['gps_retry_accuracy_m']}m/{cfg['gps_retry_timeout_s']}s).\n\n"
        f"2. Cât timp înregistrarea e activă, determină poziția la un interval care depinde de viteză: "
        f"{cfg['moving_interval_min']} min dacă tractorul se mișcă (peste {cfg['speed_threshold_kmh']} km/h), "
        f"{cfg['stationary_interval_min']} min dacă stă. Cât timp stă, verifică și accelerometrul, ca să "
        f"detecteze rapid o repornire fără să aștepte intervalul complet.\n\n"
        f"3. La fiecare {cfg['session_duration_hours']} ore trimite traseul acumulat ca fișier KMZ pe Telegram "
        f"(cu distanță/durată/viteză medie), arhivează local o copie, apoi continuă înregistrarea neîntrerupt. "
        f"Dacă trimiterea eșuează (semnal absent), reîncearcă la ciclul următor fără să piardă puncte.\n\n"
        f"4. /stop_rec trimite imediat traseul curent ca KMZ și oprește înregistrarea.\n\n"
        f"5. Indiferent dacă înregistrarea e activă: verifică periodic dacă GPS-ul e dezactivat (avertizare "
        f"Telegram + notificare persistentă pe telefon) și dacă bateria scade sub "
        f"{cfg['battery_low_threshold_pct']}% (avertizare LOW BATTERY), cu memento periodic cât timp problema "
        f"persistă.\n\n"
        f"6. Toate evenimentele sunt scrise într-un jurnal local cu rotație automată, recuperabil oricând cu "
        f"/getlogfile. Scriptul pornește automat la repornirea telefonului și se protejează împotriva rulării "
        f"a două instanțe simultan.\n\n"
        f"7. Doar chat-urile autorizate pot da comenzi — proprietarul e autorizat automat; alte conturi trebuie "
        f"să trimită întâi /login <parola>.\n\n"
        f"8. Între orele {cfg['night_autostop_start_hour']}:00–{cfg['night_autostop_end_hour']}:00, dacă nu "
        f"există nicio mișcare (nici GPS, nici accelerometru) de {cfg['night_autostop_inactivity_min']} min, "
        f"înregistrarea se oprește automat și primești mesajul „LIPSA MISCARE. INREGISTRAREA A FOST OPRITA” + "
        f"traseul ca KMZ.\n\n"
        f"9. Cât timp nu se înregistrează: dacă cel puțin {cfg['autostart_motion_ratio'] * 100:.0f}% din "
        f"ultimele {cfg['autostart_window_size']} verificări ale accelerometrului arată mișcare, ia un fix GPS; "
        f"dacă viteza confirmă peste {cfg['speed_threshold_kmh']} km/h, pornește înregistrarea automat și te "
        f"anunță pe Telegram.\n\n"
        f"10. Acest tracker are un nume propriu (util cu mai multe tractoare active simultan), setabil cu "
        f"/rename și afișat cu /name. Numele apare în fiecare fișier KMZ, în formatul „[nume] [an-lună-zi] "
        f"oraSTART [oră.minut.secundă]” cu dată/oră locală. Dacă nu are nume, primești o avertizare la fiecare "
        f"pornire a scriptului.\n\n"
        f"Comenzi: /start_rec /stop_rec /status /map /rec_status /name /rename /batt /version /getlogfile "
        f"/description /help /login /set_moving_interval /set_stationary_interval /set_speed_threshold"
    )


def interruptible_sleep(total_seconds, command_queue, check_motion,
                         accel_threshold, accel_check_interval, motion_state, tick=5):
    end = time.monotonic() + total_seconds
    last_accel_check = 0.0
    while True:
        now = time.monotonic()
        if now >= end:
            return "elapsed"
        if not command_queue.empty():
            return "command"
        if check_motion and (now - last_accel_check) >= accel_check_interval:
            last_accel_check = now
            if sensors.is_motion_detected(accel_threshold):
                motion_state["last_motion_time"] = time.monotonic()
                return "motion"
        time.sleep(min(tick, max(0.0, end - now)))


def format_point_message(prefix, point):
    return (f"{prefix}: {point['lat']:.6f}, {point['lon']:.6f} "
            f"(±{point['accuracy']:.0f}m, {point['speed_kmh']} km/h) @ {point['time']}")


def flush_pending(bot):
    track_store.ensure_dirs()
    for kmz_path in sorted(track_store.PENDING_DIR.glob("*.kmz")):
        caption_path = track_store.PENDING_DIR / f"{kmz_path.name}.caption.txt"
        caption = caption_path.read_text(encoding="utf-8") if caption_path.exists() else None
        if bot.send_document(kmz_path, caption=caption):
            shutil.move(str(kmz_path), str(track_store.ARCHIVE_DIR / kmz_path.name))
            if caption_path.exists():
                caption_path.unlink()
            logger.info("KMZ trimis și arhivat: %s", kmz_path.name)
        else:
            logger.warning("Trimitere KMZ eșuată (%s), reîncerc la următorul ciclu", kmz_path.name)
            break  # probabil fără semnal — se reîncearcă la următorul ciclu


def _sanitize_filename_part(text):
    return re.sub(r'[\\/:*?"<>|]', "_", text.strip())


def finalize_session(bot, cfg):
    points = track_store.load_points()
    track_store.clear_session()
    if not points:
        return
    track_store.ensure_dirs()
    # Points are stored with UTC timestamps; the filename must show local time.
    started_local = datetime.fromisoformat(points[0]["time"]).astimezone()
    tracker_name = (cfg.get("tracker_name") or "").strip()
    name_part = _sanitize_filename_part(tracker_name) if tracker_name else "FaraNume"
    date_part = started_local.strftime("%y%m%d")
    time_part = started_local.strftime("%H.%M.%S")
    kmz_name = f"{name_part} {date_part} oraSTART {time_part}.kmz"
    kmz_path = track_store.PENDING_DIR / kmz_name
    kml_export.export_kmz(points, kmz_path, title=f"Traseu {tracker_name or 'tractor'} {date_part} {time_part}")
    summary = kml_export.compute_summary(points)
    caption = (f"Traseu {tracker_name or '(fără nume)'} {date_part} {time_part}: {summary['distance_km']} km, "
               f"{summary['duration_min']} min, medie {summary['avg_speed_kmh']} km/h")
    (track_store.PENDING_DIR / f"{kmz_name}.caption.txt").write_text(caption, encoding="utf-8")
    logger.info("Sesiune finalizată: %d puncte, %s", len(points), caption)
    flush_pending(bot)


def check_night_autostop(bot, cfg, motion_state, points):
    """Stops the recording if we're in the configured night window and
    there's been no real movement (GPS speed nor accelerometer) for the
    configured inactivity window. Wraps past midnight (e.g. 22:00-06:00) so
    it keeps applying through the whole night, not just before midnight."""
    if not cfg.get("night_autostop_enabled", True):
        return False

    hour = datetime.now().hour
    start_h, end_h = cfg["night_autostop_start_hour"], cfg["night_autostop_end_hour"]
    in_window = (hour >= start_h or hour < end_h) if start_h > end_h else (start_h <= hour < end_h)
    if not in_window:
        return False

    inactivity_min = cfg["night_autostop_inactivity_min"]
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=inactivity_min)
    recent_points = [p for p in points if datetime.fromisoformat(p["time"]) >= cutoff]
    if not recent_points:
        return False  # not enough history yet to judge
    if any(p["speed_kmh"] >= cfg["speed_threshold_kmh"] for p in recent_points):
        return False

    if (time.monotonic() - motion_state["last_motion_time"]) < inactivity_min * 60:
        return False

    logger.warning("Lipsă mișcare de %d min în fereastra de noapte — opresc înregistrarea automat",
                    inactivity_min)
    finalize_session(bot, cfg)
    bot.send_message("LIPSA MISCARE. INREGISTRAREA A FOST OPRITA")
    return True


def begin_session(bot, cfg, motion_state, point, chat_id=None):
    track_store.start_session()
    track_store.append_point(point)
    motion_state["last_motion_time"] = time.monotonic()
    name = (cfg.get("tracker_name") or "").strip()
    name_note = f"tracker: '{name}'" if name else "tracker FĂRĂ NUME — setează cu /rename"
    logger.info("Înregistrare pornită (tracker v%s, nume=%s)", VERSION, name or "(nesetat)")
    bot.send_message(f"Am pornit înregistrarea GPS cu tracker v{VERSION} ({name_note})", chat_id=chat_id)
    bot.send_message(format_point_message("Înregistrare pornită", point), chat_id=chat_id)


def start_recording_flow(bot, cfg, gps_alert, motion_state, chat_id):
    if track_store.has_active_session():
        bot.send_message("Înregistrarea este deja activă.", chat_id=chat_id)
        return True
    if not gps.check_gps_enabled():
        handle_gps_status(False, bot, gps_alert, cfg)
        while not gps.check_gps_enabled():
            time.sleep(10)
        handle_gps_status(True, bot, gps_alert, cfg)
    point = gps.get_fix_with_retry(cfg, on_retry_message=lambda t: bot.send_message(t, chat_id=chat_id))
    if point is None:
        bot.send_message("Nu am putut determina locația. Procesul start.GPS.rec a fost anulat.", chat_id=chat_id)
        return False
    begin_session(bot, cfg, motion_state, point, chat_id)
    return True


def auto_start_watchdog(bot, cfg, motion_state, stop_event):
    """Watches the accelerometer while nothing is being recorded, using a
    sliding window over the last autostart_window_size checks instead of
    requiring every single one to show motion -- a strict all-or-nothing
    streak turned out to be unrealistically fragile in practice (a single
    quiet moment, e.g. a stoplight or smooth road, reset the whole 10-minute
    streak to zero and it never fired across a real 3-hour drive, see
    conversation from 2026-08-04). Once at least autostart_motion_ratio of
    the window is "moving", takes a GPS fix; if the speed confirms real
    driving (not just someone walking past), starts recording automatically."""
    if stop_event.wait(15):
        return
    window = deque(maxlen=cfg["autostart_window_size"])
    while not stop_event.is_set():
        try:
            if window.maxlen != cfg["autostart_window_size"]:
                window = deque(window, maxlen=cfg["autostart_window_size"])

            if not cfg.get("autostart_enabled", True) or track_store.has_active_session():
                window.clear()
            else:
                window.append(sensors.is_motion_detected(cfg["accel_motion_threshold"]))

                if len(window) == window.maxlen:
                    ratio = sum(window) / len(window)
                    if ratio >= cfg["autostart_motion_ratio"]:
                        logger.info("Mișcare în %.0f%% din ultimele %d verificări — verific GPS pentru pornire automată",
                                    ratio * 100, len(window))
                        point = gps.get_fix_within(cfg["gps_accuracy_m"], cfg["gps_timeout_s"])
                        window.clear()  # re-arm regardless of outcome, evită verificări GPS repetate la fiecare ciclu
                        if point is not None and point["speed_kmh"] > cfg["speed_threshold_kmh"]:
                            timestamp = datetime.now().strftime("%d%m%y %H.%M.%S")
                            bot.send_message(
                                f"ACCELEROMETRUL A DETECTAT MISCARE. INREGISTRAREA GPS A FOST PORNITA AUTOMAT LA {timestamp}"
                            )
                            begin_session(bot, cfg, motion_state, point)
                        else:
                            logger.info("Pornire automată: viteză sub prag sau fix indisponibil, reiau monitorizarea")
        except Exception:
            logger.exception("Eroare neașteptată în auto_start_watchdog, continui")

        stop_event.wait(cfg["autostart_check_interval_s"])


def stop_recording_flow(bot, cfg, chat_id):
    if not track_store.has_active_session():
        bot.send_message("Nu există o înregistrare activă.", chat_id=chat_id)
        return
    logger.info("Înregistrare oprită la cerere (/stop_rec)")
    finalize_session(bot, cfg)
    bot.send_message("Am încetat înregistrarea GPS", chat_id=chat_id)


def _parse_float(bot, args, label, chat_id):
    if not args:
        bot.send_message(f"Lipsește valoarea pentru {label}.", chat_id=chat_id)
        return None
    try:
        return float(args[0])
    except ValueError:
        bot.send_message(f"Valoare invalidă pentru {label}: {args[0]}", chat_id=chat_id)
        return None


def _parse_int(bot, args, label, chat_id, min_value=1):
    if not args:
        bot.send_message(f"Lipsește valoarea pentru {label}.", chat_id=chat_id)
        return None
    try:
        value = int(args[0])
    except ValueError:
        bot.send_message(f"Valoare invalidă pentru {label}: {args[0]}", chat_id=chat_id)
        return None
    if value < min_value:
        bot.send_message(f"Valoare prea mică pentru {label} (minim {min_value}).", chat_id=chat_id)
        return None
    return value


def handle_command(cmd, args, chat_id, bot, cfg, recording, gps_alert, motion_state, authorized_chats, secrets):
    if cmd == "/login":
        if args and args[0] == secrets.get("bot_password"):
            authorized_chats.add(chat_id)
            logger.info("Chat %s autentificat cu succes", chat_id)
            bot.send_message("Autentificare reușită. Poți folosi comenzile botului.", chat_id=chat_id)
        else:
            logger.warning("Încercare de autentificare eșuată de la chat %s", chat_id)
            bot.send_message("Parolă greșită.", chat_id=chat_id)
        return recording

    if chat_id not in authorized_chats:
        bot.send_message("Acces neautorizat. Trimite /login <parola>.", chat_id=chat_id)
        return recording

    if cmd == "/start_rec":
        return start_recording_flow(bot, cfg, gps_alert, motion_state, chat_id)

    if cmd == "/stop_rec":
        stop_recording_flow(bot, cfg, chat_id)
        return False

    if cmd == "/status":
        point = gps.get_fix_with_retry(cfg, on_retry_message=lambda t: bot.send_message(t, chat_id=chat_id))
        bot.send_message(format_point_message("Poziție curentă", point) if point
                          else "Nu am putut determina locația.", chat_id=chat_id)
        return recording

    if cmd == "/map":
        point = gps.get_fix_with_retry(cfg, on_retry_message=lambda t: bot.send_message(t, chat_id=chat_id))
        bot.send_message(f"https://maps.google.com/?q={point['lat']},{point['lon']}" if point
                          else "Nu am putut determina locația.", chat_id=chat_id)
        return recording

    if cmd == "/rec_status":
        if track_store.has_active_session():
            points = track_store.load_points()
            started = track_store.get_session_start()
            elapsed_min = (datetime.now(timezone.utc) - started).total_seconds() / 60
            bot.send_message(
                f"Înregistrare ACTIVĂ — pornită acum {elapsed_min:.0f} min, {len(points)} puncte înregistrate.",
                chat_id=chat_id,
            )
        else:
            bot.send_message("Înregistrare INACTIVĂ.", chat_id=chat_id)
        return recording

    if cmd == "/name":
        name = (cfg.get("tracker_name") or "").strip()
        bot.send_message(f"Nume tracker: '{name}'" if name
                          else "Tracker fără nume setat. Folosește /rename <nume>.", chat_id=chat_id)
        return recording

    if cmd == "/rename":
        if not args:
            bot.send_message("Lipsește numele. Exemplu: /rename Tractor Nord", chat_id=chat_id)
            return recording
        new_name = " ".join(args).strip()
        cfg["tracker_name"] = new_name
        save_runtime_config(cfg)
        bot.name_prefix = new_name
        logger.info("Tracker redenumit: '%s'", new_name)
        bot.send_message(f"Nume tracker setat: '{new_name}'", chat_id=chat_id)
        return recording

    if cmd == "/set_moving_interval":
        value = _parse_float(bot, args, "interval în mișcare", chat_id)
        if value is not None:
            cfg["moving_interval_min"] = value
            save_runtime_config(cfg)
            bot.send_message(f"Interval în mișcare setat la {value} min", chat_id=chat_id)
        return recording

    if cmd == "/set_stationary_interval":
        value = _parse_float(bot, args, "interval staționar", chat_id)
        if value is not None:
            cfg["stationary_interval_min"] = value
            save_runtime_config(cfg)
            bot.send_message(f"Interval staționar setat la {value} min", chat_id=chat_id)
        return recording

    if cmd == "/set_speed_threshold":
        value = _parse_float(bot, args, "prag viteză", chat_id)
        if value is not None:
            cfg["speed_threshold_kmh"] = value
            save_runtime_config(cfg)
            bot.send_message(f"Prag viteză setat la {value} km/h", chat_id=chat_id)
        return recording

    if cmd == "/set_accel_threshold":
        value = _parse_float(bot, args, "prag accelerometru", chat_id)
        if value is not None:
            cfg["accel_motion_threshold"] = value
            save_runtime_config(cfg)
            bot.send_message(f"Prag accelerometru setat la {value}", chat_id=chat_id)
        return recording

    if cmd == "/set_autostart_interval":
        value = _parse_int(bot, args, "interval verificare accelerometru (secunde)", chat_id, min_value=5)
        if value is not None:
            cfg["autostart_check_interval_s"] = value
            save_runtime_config(cfg)
            bot.send_message(f"Interval verificare accelerometru (cât timp înregistrarea e oprită) setat la {value}s",
                              chat_id=chat_id)
        return recording

    if cmd == "/set_autostart_window":
        value = _parse_int(bot, args, "dimensiune fereastră pornire automată", chat_id, min_value=2)
        if value is not None:
            cfg["autostart_window_size"] = value
            save_runtime_config(cfg)
            bot.send_message(f"Fereastră pornire automată setată la {value} verificări", chat_id=chat_id)
        return recording

    if cmd == "/set_autostart_ratio":
        value = _parse_float(bot, args, "prag procent mișcare pornire automată", chat_id)
        if value is not None:
            if not (0 < value <= 1):
                bot.send_message("Valoare invalidă (trebuie să fie între 0 și 1, ex. 0.6 pentru 60%).", chat_id=chat_id)
                return recording
            cfg["autostart_motion_ratio"] = value
            save_runtime_config(cfg)
            bot.send_message(f"Prag procent mișcare pornire automată setat la {value * 100:.0f}%", chat_id=chat_id)
        return recording

    if cmd == "/batt":
        bot.send_message(format_battery_message(device.get_battery_status()), chat_id=chat_id)
        return recording

    if cmd == "/version":
        bot.send_message(f"Tractor Tracker v{VERSION} (PID {os.getpid()})", chat_id=chat_id)
        return recording

    if cmd == "/update":
        bot.send_message("Verific actualizări din Git...", chat_id=chat_id)
        try:
            result = subprocess.run(
                ["git", "-C", str(BASE_DIR), "pull", "--ff-only"],
                capture_output=True, text=True, timeout=60,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            bot.send_message(f"Actualizare eșuată: {e}", chat_id=chat_id)
            return recording
        output = (result.stdout + result.stderr).strip()
        logger.info("git pull (/update): cod=%s ieșire=%s", result.returncode, output.replace("\n", " | "))
        if result.returncode != 0:
            bot.send_message(f"Actualizare eșuată:\n{output[-500:]}", chat_id=chat_id)
            return recording
        if "already up to date" in output.lower() or "already up-to-date" in output.lower():
            bot.send_message("Deja la ultima versiune.", chat_id=chat_id)
            return recording
        bot.send_message(f"Cod nou descărcat, repornesc scriptul...\n{output[-300:]}", chat_id=chat_id)
        logger.info("Repornire proces după /update")
        # Repornim procesul cu os.execv (nu doar exit) ca actualizarea să nu
        # depindă de bucla de supervizare (install/boot-start-tracker.sh) --
        # aceea s-a dovedit că poate muri neobservat (vezi conversația din
        # 2026-08-06), iar fără ea un exit simplu ar opri totul definitiv.
        # Descriptorul lacătului de instanță unică e non-inheritable by
        # default în Python 3.4+ (PEP 446), deci exec îl închide și eliberează
        # flock-ul automat -- îl închidem explicit oricum, ca să fim siguri.
        if _pid_lock_fd is not None:
            try:
                fcntl.flock(_pid_lock_fd, fcntl.LOCK_UN)
                _pid_lock_fd.close()
            except OSError:
                pass
        os.execv(sys.executable, [sys.executable] + sys.argv)

    if cmd == "/description":
        bot.send_message(build_description(cfg), chat_id=chat_id)
        return recording

    if cmd == "/getlogfile":
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 0:
            bot.send_document(LOG_PATH, caption="Jurnal tractor tracker", chat_id=chat_id)
        else:
            bot.send_message("Nu există încă înregistrări în fișierul de log.", chat_id=chat_id)
        return recording

    if cmd == "/help":
        bot.send_message(
            "/start_rec — pornește înregistrarea\n"
            "/stop_rec — oprește și trimite traseul\n"
            "/status — poziție instantanee\n"
            "/map — link Google Maps către poziția curentă\n"
            "/rec_status — arată dacă înregistrarea e activă acum\n"
            "/name — numele curent al acestui tracker\n"
            "/rename <nume> — schimbă numele acestui tracker\n"
            "/batt — starea bateriei telefonului\n"
            "/version — versiunea codului care rulează\n"
            "/update — descarcă ultima versiune din Git și repornește scriptul\n"
            "/description — cum funcționează scriptul, cu setările active\n"
            "/getlogfile — trimite fișierul de log curent\n"
            "/set_moving_interval <min>\n"
            "/set_stationary_interval <min>\n"
            "/set_speed_threshold <kmh>\n"
            "/set_accel_threshold <valoare> — prag sensibilitate accelerometru\n"
            "/set_autostart_interval <secunde> — cât de des verifică accelerometrul cât timp înregistrarea e oprită\n"
            "/set_autostart_window <n> — câte verificări intră în fereastra de pornire automată\n"
            "/set_autostart_ratio <0-1> — ce procent din fereastră trebuie să arate mișcare (ex. 0.6)\n"
            "/login <parola> — autorizează acest chat să folosească botul\n"
            "Într-un grup cu mai multe tractoare, adaugă @numele_botului la comandă "
            "(ex. /update@Tractor1_bot) ca să știe care tractor o primește.",
            chat_id=chat_id,
        )
        return recording

    bot.send_message("Comandă necunoscută. /help pentru listă.", chat_id=chat_id)
    return recording


def main():
    secrets = load_config()
    cfg = load_runtime_config()
    bot = TelegramBot(secrets["bot_token"], secrets["allowed_chat_id"])
    bot.name_prefix = (cfg.get("tracker_name") or "").strip()

    if not acquire_single_instance_lock():
        existing_pid = PID_FILE_PATH.read_text(encoding="utf-8").strip() if PID_FILE_PATH.exists() else "?"
        logger.error("O altă instanță rulează deja (PID %s) — ies.", existing_pid)
        bot.send_message(
            f"Tractor Tracker v{VERSION} (PID {os.getpid()}): o altă instanță "
            f"(PID {existing_pid}) rulează deja pe acest telefon — pornirea a fost anulată."
        )
        sys.exit(1)

    track_store.ensure_dirs()

    command_queue = queue.Queue()
    stop_event = threading.Event()
    gps_alert = {"active": False, "last_reminder": 0.0}
    battery_alert = {"active": False, "last_reminder": 0.0}
    motion_state = {"last_motion_time": time.monotonic()}
    authorized_chats = {secrets["allowed_chat_id"]}
    threading.Thread(target=telegram_listener, args=(bot, command_queue, stop_event),
                      daemon=True).start()
    threading.Thread(target=gps_watchdog, args=(bot, cfg, gps_alert, stop_event),
                      daemon=True).start()
    threading.Thread(target=battery_watchdog, args=(bot, cfg, battery_alert, stop_event),
                      daemon=True).start()
    threading.Thread(target=auto_start_watchdog, args=(bot, cfg, motion_state, stop_event),
                      daemon=True).start()

    recording = track_store.has_active_session()
    tracker_name = (cfg.get("tracker_name") or "").strip()
    name_note = f"tracker: '{tracker_name}'" if tracker_name else "tracker FĂRĂ NUME"
    logger.info("Tractor Tracker v%s (PID %s) pornit (recording=%s, nume=%s)",
                VERSION, os.getpid(), recording, tracker_name or "(nesetat)")
    bot.send_message(
        f"Reluare înregistrare după repornire (tracker v{VERSION}, PID {os.getpid()}, {name_note})." if recording
        else f"Tractor Tracker v{VERSION} pornit (PID {os.getpid()}, {name_note}). Trimite /start_rec pentru a începe."
    )
    if not tracker_name:
        bot.send_message(
            "ATENTIE: acest tracker nu are un nume setat. Cu mai multe tractoare active simultan, "
            "fișierele KMZ nu vor putea fi identificate ușor. Setează un nume cu /rename <nume>."
        )

    while True:
        # Re-sincronizează cu starea persistată de fiecare dată -- track_store
        # e sursa de adevăr. Necesar mai ales pentru auto_start_watchdog, care
        # rulează într-un fir separat și pornește sesiunea direct (begin_session)
        # fără să poată actualiza variabila locală `recording` de mai jos; fără
        # sincronizarea asta, bucla principală rămânea blocată în ramura
        # "nu înregistrez" la nesfârșit după o pornire automată, deși sesiunea
        # exista deja pe disc (niciun punct/KMZ/alertă în plus, dar și fără nicio
        # eroare -- diagnosticat din jurnal, 2026-08-05).
        new_recording = track_store.has_active_session()
        if new_recording != recording:
            logger.info("Stare recording: %s -> %s", recording, new_recording)
        recording = new_recording

        while not command_queue.empty():
            chat_id, cmd, args = command_queue.get()
            recording = handle_command(cmd, args, chat_id, bot, cfg, recording, gps_alert,
                                        motion_state, authorized_chats, secrets)

        flush_pending(bot)

        if recording:
            points = track_store.load_points()
            last_speed = points[-1]["speed_kmh"] if points else 0
            stationary = last_speed <= cfg["speed_threshold_kmh"]
            if not stationary:
                motion_state["last_motion_time"] = time.monotonic()
            interval_s = (cfg["stationary_interval_min"] if stationary
                          else cfg["moving_interval_min"]) * 60

            reason = interruptible_sleep(
                interval_s, command_queue,
                check_motion=stationary,
                accel_threshold=cfg["accel_motion_threshold"],
                accel_check_interval=cfg["accel_check_interval_s"],
                motion_state=motion_state,
            )
            if reason == "command":
                continue

            point = gps.get_fix_within(cfg["gps_accuracy_m"], cfg["gps_timeout_s"])
            if point is not None:
                track_store.append_point(point)
                logger.info("Punct înregistrat: lat=%.6f lon=%.6f acc=%.0fm viteza=%.1fkm/h (%s)",
                            point["lat"], point["lon"], point["accuracy"], point["speed_kmh"],
                            "staționar" if stationary else "mișcare")

            if check_night_autostop(bot, cfg, motion_state, track_store.load_points() if point else points):
                recording = False
                continue

            started = track_store.get_session_start()
            elapsed_h = (datetime.now(timezone.utc) - started).total_seconds() / 3600
            if elapsed_h >= cfg["session_duration_hours"]:
                finalize_session(bot, cfg)
                track_store.start_session()
                if point is not None:
                    track_store.append_point(point)
        else:
            time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Eroare fatală neașteptată — scriptul se oprește.")
        raise
