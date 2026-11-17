import datetime
import logging

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

    root.info("Logger initialized. Log file: %s", _log_file)

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
            log.info("Deleted old log file: %s", path)
        except OSError as e:
            log.warning("Failed to delete old log file %s: %s", path, e)


def get_log_file_path():
    """This run's log file, or None when logging was never configured."""
    return _log_file
