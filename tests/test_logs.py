import logging
import tempfile
import unittest
from logging.handlers import RotatingFileHandler
from pathlib import Path
from unittest import mock

from emulator.logs import configure_logging


class LoggingTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def configure(self, log_dir):
        handler = configure_logging(log_dir)

        # Fecha o arquivo antes de apagar a pasta temporária; o Windows não apaga arquivo aberto.
        def detach():
            logging.getLogger("emulator").removeHandler(handler)
            handler.close()

        self.addCleanup(detach)
        return handler

    def test_terminal_without_folder(self):
        handler = self.configure(None)

        self.assertIsInstance(handler, logging.StreamHandler)
        self.assertNotIsInstance(handler, RotatingFileHandler)

    def test_file_rotates_and_keeps_three_backups(self):
        with mock.patch("emulator.logs.MAX_LOG_BYTES", 300):
            self.configure(self.folder / "data")

        logger = logging.getLogger("emulator.server")
        for index in range(100):
            logger.info("Linha %d de teste, com texto para encher o arquivo.", index)

        names = sorted(path.name for path in (self.folder / "data").iterdir())
        self.assertEqual(names, ["emulator.log", "emulator.log.1", "emulator.log.2", "emulator.log.3"])

    def test_reconfiguring_replaces_the_previous_destination(self):
        self.configure(self.folder)
        self.configure(None)

        handlers = logging.getLogger("emulator").handlers
        self.assertEqual(len(handlers), 1)
        self.assertNotIsInstance(handlers[0], RotatingFileHandler)


if __name__ == "__main__":
    unittest.main()
