import logging

import requests

logger = logging.getLogger("tractor_tracker.telegram")

API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramBot:
    def __init__(self, token, allowed_chat_id):
        self.token = token
        self.allowed_chat_id = allowed_chat_id
        self._offset = 0
        # Prefixul de identificare a tractorului -- setat de main.py din
        # cfg["tracker_name"] la pornire și reîmprospătat la fiecare /rename,
        # ca să se poată distinge mesajele mai multor tractoare active
        # simultan în același chat Telegram (vezi conversația din 2026-08-06).
        self.name_prefix = ""

    def _url(self, method):
        return API_BASE.format(token=self.token, method=method)

    def send_message(self, text, chat_id=None):
        if self.name_prefix:
            text = f"[{self.name_prefix}] {text}"
        try:
            requests.post(
                self._url("sendMessage"),
                data={"chat_id": chat_id or self.allowed_chat_id, "text": text},
                timeout=15,
            )
            return True
        except requests.RequestException as e:
            logger.warning("Eșec trimitere mesaj Telegram: %s", e)
            return False

    def send_document(self, file_path, caption=None, chat_id=None):
        if self.name_prefix:
            caption = f"[{self.name_prefix}] {caption}" if caption else f"[{self.name_prefix}]"
        try:
            with open(file_path, "rb") as f:
                data = {"chat_id": chat_id or self.allowed_chat_id}
                if caption:
                    data["caption"] = caption
                resp = requests.post(
                    self._url("sendDocument"),
                    data=data,
                    files={"document": f},
                    timeout=60,
                )
            if resp.status_code != 200:
                logger.warning("Eșec trimitere fișier %s: HTTP %s", file_path, resp.status_code)
            return resp.status_code == 200
        except (requests.RequestException, OSError) as e:
            logger.warning("Eșec trimitere fișier %s: %s", file_path, e)
            return False

    def poll_commands(self, timeout_s=25):
        """Long-poll getUpdates and return (chat_id, command, args) tuples for
        every command-like message received, from any chat. Authorization
        (password / whitelist) is enforced by the caller, not here."""
        try:
            resp = requests.get(
                self._url("getUpdates"),
                params={"offset": self._offset, "timeout": timeout_s},
                timeout=timeout_s + 10,
            )
            resp.raise_for_status()
            updates = resp.json().get("result", [])
        except requests.RequestException as e:
            logger.debug("Eșec poll Telegram (probabil fără semnal): %s", e)
            return []

        commands = []
        for update in updates:
            self._offset = max(self._offset, update["update_id"] + 1)
            message = update.get("message") or {}
            chat_id = message.get("chat", {}).get("id")
            text = message.get("text", "")
            if chat_id is None or not text.startswith("/"):
                continue
            parts = text.strip().split()
            # Într-un grup cu mai multe boturi (câte unul per tractor),
            # Telegram livrează o comandă "/cmd@NumeBot" DOAR botului vizat --
            # celelalte nici n-o primesc prin getUpdates. Trebuie doar să
            # tăiem sufixul "@NumeBot" ca să se potrivească cu "/cmd" de mai
            # jos; nu mai verificăm noi cui îi era adresată, Telegram a
            # făcut deja filtrarea aia (vezi conversația din 2026-08-06).
            cmd = parts[0].lower().split("@", 1)[0]
            commands.append((chat_id, cmd, parts[1:]))
        return commands
