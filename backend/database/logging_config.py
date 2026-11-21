"""
Centralized logging configuration for database scripts.

This module provides a standardized logging setup that creates log files
in backend/database/logs/ with timestamps and script names.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional


def setup_logging(
    script_name: Optional[str] = None,
    log_level: int = logging.INFO,
    log_dir: str = "backend/database/logs",
) -> logging.Logger:
    """
    Set up centralized logging for database scripts.

    Args:
        script_name: Name of the script (auto-detected if None)
        log_level: Logging level (default: INFO)
        log_dir: Directory for log files (default: backend/database/logs)

    Returns:
        Configured logger instance
    """
    if script_name is None:
        import inspect

        frame = inspect.currentframe()
        if frame and frame.f_back and frame.f_back.f_code:
            script_path = frame.f_back.f_code.co_filename
            script_name = Path(script_path).stem
        else:
            script_name = "unknown_script"

    log_dir_path = Path(log_dir)
    log_dir_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"{script_name}_{timestamp}.log"
    log_file_path = log_dir_path / log_filename

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file_path),
            logging.StreamHandler(),
        ],
        force=True,
    )

    logger = logging.getLogger(script_name)
    logger.info(f"Logging initialized for {script_name}")
    logger.info(f"Log file: {log_file_path}")

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
