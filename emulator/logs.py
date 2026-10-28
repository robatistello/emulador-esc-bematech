"""Registro de eventos: na tela pelo terminal, em arquivo com rotação na bandeja."""

import logging
from logging.handlers import RotatingFileHandler

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_FILE_NAME = "emulator.log"
MAX_LOG_BYTES = 1024 * 1024
BACKUP_COUNT = 3


def configure_logging(log_dir=None):
    """Sem pasta, registra no terminal; com pasta, num arquivo que nunca passa de uns 4 MB."""
    logger = logging.getLogger("emulator")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    if log_dir is None:
        handler = logging.StreamHandler()
    else:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / LOG_FILE_NAME, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )

    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)
    return handler
