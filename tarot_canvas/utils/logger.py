import datetime
import logging
from typing import ClassVar

from tarot_canvas.utils.path_helper import get_data_directory

LOGGER_NAME = "tarot_canvas"
FORMAT = "%(asctime)s - %(levelname)s - %(name)s:%(lineno)d - %(message)s"

# A log is deleted only when it is neither one of the newest KEEP_NEWEST nor younger than
# KEEP_DAYS, so a crash reported the next day, or after a dozen relaunches, is still there
KEEP_NEWEST = 20
KEEP_DAYS = 7

_log_file = None


def configure_logging(log_dir=None):
    """Open this run's log file and prune old ones. Only main() calls this.

    Importing the package configures nothing, so a test, a bench run or a one-off
    import neither creates a log file nor deletes one.
    """
    global _log_file

    if log_dir is None:
        log_dir = get_data_directory("tarot-canvas/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    _log_file = log_dir / f"tarot_canvas_{timestamp}.log"

    formatter = logging.Formatter(FORMAT)

    file_handler = logging.FileHandler(_log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    root = logging.getLogger(LOGGER_NAME)
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    root.info(f"Logger initialized. Log file: {_log_file}")

    # After the new file exists, so this run is always one of the newest
    prune_logs(log_dir)

    return _log_file


def prune_logs(log_dir, keep_newest=KEEP_NEWEST, keep_days=KEEP_DAYS, now=None):
    """Delete the logs that are neither among the newest keep_newest nor keep_days old."""
    log = logging.getLogger(LOGGER_NAME)
    now = now or datetime.datetime.now()
    cutoff = (now - datetime.timedelta(days=keep_days)).timestamp()

    logs = sorted(
        log_dir.glob("tarot_canvas_*.log"), key=lambda path: path.stat().st_mtime, reverse=True
    )
    for path in logs[keep_newest:]:
        if path.stat().st_mtime >= cutoff:
            continue
        try:
            path.unlink()
            log.info(f"Deleted old log file: {path}")
        except OSError as e:
            log.warning(f"Failed to delete old log file {path}: {e}")


def get_log_file_path():
    """This run's log file, or None when logging was never configured."""
    return _log_file


class TarotLogger:
    """Logs to the tarot_canvas logger and tells the log viewer"""

    _logger = logging.getLogger(LOGGER_NAME)
    _subscribers: ClassVar[list] = []

    @classmethod
    def debug(cls, message):
        """Log a debug message"""
        cls._logger.debug(message)
        cls._notify_subscribers(logging.DEBUG, message)

    @classmethod
    def info(cls, message):
        """Log an info message"""
        cls._logger.info(message)
        cls._notify_subscribers(logging.INFO, message)

    @classmethod
    def warning(cls, message):
        """Log a warning message"""
        cls._logger.warning(message)
        cls._notify_subscribers(logging.WARNING, message)

    @classmethod
    def error(cls, message):
        """Log an error message"""
        cls._logger.error(message)
        cls._notify_subscribers(logging.ERROR, message)

    @classmethod
    def exception(cls, message):
        """Log an error message with the traceback of the exception being handled"""
        cls._logger.exception(message)
        cls._notify_subscribers(logging.ERROR, message)

    @classmethod
    def critical(cls, message):
        """Log a critical message"""
        cls._logger.critical(message)
        cls._notify_subscribers(logging.CRITICAL, message)

    @classmethod
    def subscribe(cls, callback):
        """Add a subscriber to receive log messages"""
        if callback not in cls._subscribers:
            cls._subscribers.append(callback)

    @classmethod
    def unsubscribe(cls, callback):
        """Remove a subscriber"""
        if callback in cls._subscribers:
            cls._subscribers.remove(callback)

    @classmethod
    def _notify_subscribers(cls, level, message):
        """Notify all subscribers of a new log message"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for callback in cls._subscribers:
            try:
                callback(level, timestamp, message)
            except Exception:
                cls._logger.exception("Error notifying a log subscriber")

    @classmethod
    def get_log_file_path(cls):
        """Get the current log file path"""
        return get_log_file_path()


# Every method is a classmethod, so the class is the logger; nothing runs at import
logger = TarotLogger
