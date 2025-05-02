import logging
import os
import datetime
from pathlib import Path

class TarotLogger:
    """Central logging system for Tarot Canvas application"""
    
    _instance = None
    _log_file = None
    _logger = None
    _subscribers = []
    
    @classmethod
    def get_instance(cls):
        """Singleton pattern to ensure only one logger instance exists"""
        if cls._instance is None:
            cls._instance = cls()
            cls._setup_logger()
        return cls._instance
    
    @classmethod
    def _setup_logger(cls):
        """Set up the logging infrastructure"""
        # Create logger
        cls._logger = logging.getLogger("TarotCanvas")
        cls._logger.setLevel(logging.DEBUG)
        
        # Create log directory if it doesn't exist
        log_dir = Path(os.path.expanduser("~/.local/share/tarot-canvas/logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create log file with timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        cls._log_file = log_dir / f"tarot_canvas_{timestamp}.log"
        
        # Create file handler
        file_handler = logging.FileHandler(cls._log_file)
        file_handler.setLevel(logging.DEBUG)
        
        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Add handlers to logger
        cls._logger.addHandler(file_handler)
        cls._logger.addHandler(console_handler)
        
        # Log startup message
        cls._logger.info(f"Logger initialized. Log file: {cls._log_file}")
    
    @classmethod
    def debug(cls, message):
        """Log a debug message"""
        if cls._logger is None:
            cls.get_instance()
        cls._logger.debug(message)
        cls._notify_subscribers(logging.DEBUG, message)
    
    @classmethod
    def info(cls, message):
        """Log an info message"""
        if cls._logger is None:
            cls.get_instance()
        cls._logger.info(message)
        cls._notify_subscribers(logging.INFO, message)
    
    @classmethod
    def warning(cls, message):
        """Log a warning message"""
        if cls._logger is None:
            cls.get_instance()
        cls._logger.warning(message)
        cls._notify_subscribers(logging.WARNING, message)
    
    @classmethod
    def error(cls, message):
        """Log an error message"""
        if cls._logger is None:
            cls.get_instance()
        cls._logger.error(message)
        cls._notify_subscribers(logging.ERROR, message)
    
    @classmethod
    def critical(cls, message):
        """Log a critical message"""
        if cls._logger is None:
            cls.get_instance()
        cls._logger.critical(message)
        cls._notify_subscribers(logging.CRITICAL, message)
    
    @classmethod
    def subscribe(cls, callback):
        """Add a subscriber to receive log messages"""
        if cls._instance is None:
            cls.get_instance()
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
            except Exception as e:
                print(f"Error notifying subscriber: {e}")
    
    @classmethod
    def get_log_file_path(cls):
        """Get the current log file path"""
        if cls._log_file is None:
            cls.get_instance()
        return cls._log_file

# Create a simple alias for easier imports
logger = TarotLogger.get_instance()