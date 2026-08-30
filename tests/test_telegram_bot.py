import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from telegram_bot import TelegramBot  # noqa: E402


def _fake_response(updates):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"result": updates}
    return resp


class TestPollCommandsBotUsernameSuffix(unittest.TestCase):
    """Într-un grup Telegram cu mai multe boturi (câte unul per tractor), o
    comandă vine ca '/cmd@NumeBot' -- trebuie tăiat sufixul ca să se
    potrivească handler-elor din main.py, care verifică doar '/cmd' (vezi
    conversația din 2026-08-06)."""

    def setUp(self):
        self.bot = TelegramBot("fake-token", allowed_chat_id=111)

    def _poll_with(self, text):
        update = {
            "update_id": 1,
            "message": {"chat": {"id": 111}, "text": text},
        }
        with patch("telegram_bot.requests.get", return_value=_fake_response([update])):
            return self.bot.poll_commands()

    def test_strips_bot_username_suffix(self):
        result = self._poll_with("/update@Tractor1_bot")
        self.assertEqual(result, [(111, "/update", [])])

    def test_plain_command_unaffected(self):
        result = self._poll_with("/update")
        self.assertEqual(result, [(111, "/update", [])])

    def test_suffix_with_args(self):
        result = self._poll_with("/rename@Tractor1_bot Nord")
        self.assertEqual(result, [(111, "/rename", ["Nord"])])


class TestNamePrefix(unittest.TestCase):
    """Mesajele/documentele trimise sunt prefixate cu [nume_tracker] atunci
    când e setat, ca să se distingă tractoarele într-un grup comun."""

    def setUp(self):
        self.bot = TelegramBot("fake-token", allowed_chat_id=111)

    def test_send_message_no_prefix_by_default(self):
        with patch("telegram_bot.requests.post") as mock_post:
            self.bot.send_message("salut")
            self.assertEqual(mock_post.call_args.kwargs["data"]["text"], "salut")

    def test_send_message_with_prefix(self):
        self.bot.name_prefix = "Tractor1"
        with patch("telegram_bot.requests.post") as mock_post:
            self.bot.send_message("salut")
            self.assertEqual(mock_post.call_args.kwargs["data"]["text"], "[Tractor1] salut")


if __name__ == "__main__":
    unittest.main()
