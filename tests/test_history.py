import json
import os
import sqlite3
import stat
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from emulator.escpos import Parser
from emulator.history import History
from support import parse
from tools.send_demo import qr_command


class HistoryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "history.sqlite3"
        self.history = History(self.path)

    def test_list_version_changes_after_clear_with_same_number(self):
        self.assertEqual(self.history.version(), '"empty"')

        self.history.save(parse(b"Primeiro\n")[0])
        first = self.history.version()
        self.assertEqual(self.history.version(), first)

        self.history.clear()
        self.history.save(parse(b"Outro\n")[0])
        self.assertTrue(self.history.version().startswith('"1-'))
        self.assertNotEqual(self.history.version(), first)

    def test_drawer_preview_and_binary_payload_keep_storage(self):
        drawer = parse(b"\x1d\xf9\x20\x00\x1b2\x1bt\x02\x1bv\xc8")[0]
        binary = parse(qr_command(b"A\x1bv\xc8B"))[0]

        self.history.save(drawer)
        self.history.save(binary)

        self.assertEqual(self.history.list()[1]["preview"], "Abertura da gaveta 1 · pulso de 200 ms")
        self.assertEqual(self.history.get(1)["events"][0]["drawer"], 1)
        self.assertEqual(self.history.get(1)["lines"], [])
        self.assertEqual(self.history.get(2)["events"], [])

        with closing(sqlite3.connect(self.history.path)) as connection:
            stored = json.loads(connection.execute("SELECT payload FROM jobs WHERE id=1").fetchone()[0])
        self.assertEqual(stored, drawer)

    def test_history_keeps_state_after_cut_and_restart(self):
        parser = Parser(self.history.save)
        parser.feed(b"\x1bEA\x1bwB\x1bm")
        parser.close()

        restored = History(self.path)

        self.assertEqual(len(restored.list()), 2)
        self.assertTrue(restored.get(2)["lines"][0]["spans"][0]["bold"])

    def test_keeps_only_the_most_recent_jobs(self):
        history = History(self.path, keep=2)

        for text in (b"Um\n", b"Dois\n", b"Tres\n"):
            history.save(parse(text)[0])

        self.assertEqual([job["preview"] for job in history.list()], ["Tres", "Dois"])

    def test_lower_limit_applies_on_open_and_zero_keeps_everything(self):
        for text in (b"Um\n", b"Dois\n", b"Tres\n"):
            self.history.save(parse(text)[0])

        self.assertEqual(len(History(self.path, keep=0).list()), 3)
        self.assertEqual([job["id"] for job in History(self.path, keep=1).list()], [3])

    def test_read_only_database_fails_on_open(self):
        os.chmod(self.path, stat.S_IREAD)
        self.addCleanup(os.chmod, self.path, stat.S_IREAD | stat.S_IWRITE)

        with self.assertRaises(sqlite3.Error):
            History(self.path)


if __name__ == "__main__":
    unittest.main()
