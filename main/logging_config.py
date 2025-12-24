import logging.config
import colorlog
import os

# Determine the absolute path for the log file, placing it in the same directory as this script.
log_file_path = os.path.join(os.path.dirname(__file__), 'app.log')

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'colored_formatter': {
            '()': 'colorlog.ColoredFormatter',
            'format': '%(asctime)s - %(name)s - %(log_color)s%(levelname)s%(reset)s - %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
            'log_colors': {
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            },
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO', # Set to INFO to show less verbose logs in console
            'formatter': 'colored_formatter',
            'class': 'colorlog.StreamHandler',
        },
        'file': {
            'level': 'DEBUG',
            'formatter': 'standard',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': log_file_path,
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'encoding': 'utf8',
        },
    },
    'loggers': {
        '': {  # root logger
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
    }
}

def setup_logging():
    """Load the logging configuration."""
    logging.config.dictConfig(LOGGING_CONFIG)
