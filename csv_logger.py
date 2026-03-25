"""
CSV logging functionality for recording Owlet vitals data.

This module handles initialization and writing of vitals data to a CSV file
for historical tracking and analysis.
"""

import csv
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def init_csv_logging(log_file):
    """
    Initialize CSV log file with headers if it doesn't exist.
    Creates a new file with column headers for all vital signs and metadata.
    
    Args:
        log_file: Path to the CSV log file
    """
    if not os.path.exists(log_file):
        with open(log_file, mode='w', newline='') as file:
            writer = csv.writer(file)
            headers = [
                "timestamp_log", "lag_seconds",
                "hr", "ox", "oxta", "mv", "mvb", 
                "rsi", "ss", "sc", 
                "bat", "btt", "chg",
                "onm", "bso", "bp", "mrs", "hw",
                "st", "srf"
            ]
            writer.writerow(headers)
        logger.info(f"Created log file: {log_file}")


def log_data_to_csv(log_file, vitals, lag):
    """
    Append a row of vitals data to the CSV log file.
    
    Args:
        log_file: Path to the CSV log file
        vitals: Dictionary containing all vital sign readings
        lag: Data freshness lag in seconds
    """
    with open(log_file, mode='a', newline='') as file:
        writer = csv.writer(file)
        row = [
            datetime.now().isoformat(), 
            round(lag, 1),              
            vitals.get("hr"),
            vitals.get("ox"),
            vitals.get("oxta"),
            vitals.get("mv"),
            vitals.get("mvb"),
            vitals.get("rsi"),
            vitals.get("ss"),
            vitals.get("sc"),
            vitals.get("bat"),
            vitals.get("btt"),
            vitals.get("chg"),
            vitals.get("onm"),
            vitals.get("bso"),
            vitals.get("bp"),
            vitals.get("mrs"),
            vitals.get("hw"),
            vitals.get("st"),
            vitals.get("srf")
        ]
        writer.writerow(row)
