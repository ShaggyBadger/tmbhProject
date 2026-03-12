import logging.config
import colorlog
import os

# Paths for log files
base_dir = os.path.dirname(__file__)
persistent_log_path = os.path.join(base_dir, "app.log")
debug_log_path = os.path.join(base_dir, "debug.log")

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "colored_formatter": {
            "()": "colorlog.ColoredFormatter",
            "format": "%(asctime)s - %(name)s - %(log_color)s%(levelname)s%(reset)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "log_colors": {
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        },
    },
    "handlers": {
        "console": {
            "level": "ERROR",  # Only show ERROR or CRITICAL in terminal
            "formatter": "colored_formatter",
            "class": "colorlog.StreamHandler",
        },
        "persistent_file": {
            "level": "INFO",  # INFO and above (WARNING, ERROR, CRITICAL)
            "formatter": "standard",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": persistent_log_path,
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
            "encoding": "utf8",
        },
        "debug_file": {
            "level": "DEBUG",  # Everything
            "formatter": "standard",
            "class": "logging.FileHandler",
            "filename": debug_log_path,
            "mode": "w",  # Overwrite each time
            "encoding": "utf8",
        },
    },
    "loggers": {
        "": {  # root logger
            "handlers": ["console", "persistent_file", "debug_file"],
            "level": "DEBUG",  # Capture everything at the root level
            "propagate": True,
        },
    },
}


def setup_logging():
    """Load the logging configuration."""
    logging.config.dictConfig(LOGGING_CONFIG)
