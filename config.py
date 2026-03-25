"""
Configuration settings for the Owlet Dream Logger application.

Note: Credentials are now entered via the login page.
This file only contains application-level settings.
"""

# ----------------- APPLICATION CONFIG -----------------
# Server and logging behavior
UPDATE_INTERVAL = 2  # Seconds between data fetches from the sock
LOG_FILE = "owlet_data_log.csv"  # CSV file to log all vitals data
HOST = "0.0.0.0"  # Server host (0.0.0.0 for all interfaces)
PORT = 8000  # Server port
