import logging
from logging import LogRecord, StreamHandler
from logging.handlers import TimedRotatingFileHandler
from typing import Callable

from scihub_eva.utils.path_utils import LOGS_DIR

DEFAULT_LOGGER = logging.getLogger('default')
DEFAULT_LOGGER.setLevel(logging.INFO)

DEFAULT_LOG_DIRECTORY = LOGS_DIR
DEFAULT_LOG_FILE = DEFAULT_LOG_DIRECTORY / 'SciHubEVA.log'
DEFAULT_LOG_HANDLER = TimedRotatingFileHandler(
    DEFAULT_LOG_FILE.resolve().as_posix(), when='d', encoding='utf-8'
)
DEFAULT_LOG_HANDLER.setLevel(logging.INFO)

DEFAULT_LOG_FORMATTER = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
DEFAULT_LOG_HANDLER.setFormatter(DEFAULT_LOG_FORMATTER)

DEFAULT_LOGGER.addHandler(DEFAULT_LOG_HANDLER)

LOGGER_SEP = '–' * 30


class CallbackLogHandler(StreamHandler):
    """Log handler that forwards formatted records to an arbitrary callback."""

    def __init__(self, callback: Callable[[str], None]) -> None:
        super().__init__()
        self.formatter = DEFAULT_LOG_FORMATTER
        self._callback = callback

    def emit(self, record: LogRecord) -> None:
        try:
            self._callback(self.format(record))
        except Exception:
            self.handleError(record)


__all__ = [
    'DEFAULT_LOG_DIRECTORY',
    'DEFAULT_LOG_FILE',
    'DEFAULT_LOG_HANDLER',
    'DEFAULT_LOG_FORMATTER',
    'DEFAULT_LOGGER',
    'LOGGER_SEP',
    'CallbackLogHandler',
]
