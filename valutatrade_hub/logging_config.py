import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader

LOGGER_NAME = "valutatrade.actions"


class ISOFormatter(logging.Formatter):
    """Форматирует время записи в ISO 8601 с часовым поясом UTC."""

    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created, UTC).isoformat(timespec="seconds")


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Настраивает файловый лог с ротацией без повторных обработчиков."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:
        return logger

    settings = SettingsLoader()
    log_path = Path(settings.get("log_file"))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(ISOFormatter(settings.get("log_format")))
    logger.addHandler(handler)

    return logger


def setup_parser_logging(
    log_file: str | Path | None = None,
    level: int = logging.INFO,
) -> logging.Logger:
    """Настраивает отдельный журнал обновления курсов."""

    logger = logging.getLogger("valutatrade.parser")
    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:
        return logger

    settings = SettingsLoader()
    path = (
        Path(log_file)
        if log_file is not None
        else Path(settings.get("log_file")).parent / "parser.log"
    )
    path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(ISOFormatter(settings.get("log_format")))
    logger.addHandler(handler)
    return logger
