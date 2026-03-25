"""
Background worker for continuously fetching and streaming Owlet data.

This module contains the main worker loop that authenticates, discovers devices,
fetches vitals data, and streams it via WebSocket while logging to CSV.
"""

import asyncio
import logging
from fastapi import WebSocket

from pyowletapi.api import OwletAPI
from pyowletapi.sock import Sock

from config import UPDATE_INTERVAL, LOG_FILE
from owlet_service import discover_socks
from data_processing import process_properties
from csv_logger import init_csv_logging, log_data_to_csv

logger = logging.getLogger(__name__)


def create_owlet_worker(email: str, password: str, region: str):
    """
    Create an Owlet worker function with specific credentials.
    
    Args:
        email: Owlet account email
        password: Owlet account password
        region: API region
        
    Returns:
        Async function that runs the worker
    """
    async def owlet_worker(ws: WebSocket):
        """
        Main worker function that continuously fetches and sends Owlet data.
        
        This async function:
        1. Authenticates with the Owlet API
        2. Discovers available smart sock devices
        3. Enters a loop that updates and sends data every UPDATE_INTERVAL seconds
        4. Logs all data to CSV file
        5. Sends real-time updates to the WebSocket client
        
        Args:
            ws: WebSocket connection to send data updates to the client
        """
        # Initialize CSV logging if not already created
        init_csv_logging(LOG_FILE)

        api = OwletAPI(region, email, password)
        try:
            # Authenticate with Owlet cloud service
            await api.authenticate()
            
            # Discover all smart sock devices on the account
            socks = await discover_socks(api)
            if not socks:
                # Fallback: try to use the first device if no SS3 socks found
                all_devs = await api.get_devices()
                
                # Handle both list and dict response formats
                devices_list = []
                if isinstance(all_devs, list):
                    devices_list = all_devs
                elif isinstance(all_devs, dict) and "response" in all_devs:
                    devices_list = all_devs["response"]
                
                if devices_list:
                    first_dev = devices_list[0].get("device")
                    if first_dev:
                        socks = [Sock(api, first_dev)]
                
                if not socks:
                    await ws.send_json({"error": "No sock found"})
                    return

            # Use the first discovered sock
            sock = socks[0]
            
            # Track stale data to detect connection issues
            stale_count = 0
            max_stale_before_warning = 3
            max_lag_seconds = 30  # Consider data stale if lag exceeds this
            
            # Main monitoring loop - runs continuously until connection is closed
            while True:
                # Fetch latest properties from the sock device
                result = await sock.update_properties()

                # Handle token refresh - pyowletapi returns new tokens when they change
                if isinstance(result, dict) and "tokens" in result:
                    tokens = result["tokens"]
                    if tokens:
                        logger.info("API tokens refreshed automatically")

                if sock.raw_properties:
                    # Process raw data into structured format
                    data = process_properties(sock.raw_properties)
                    
                    # Check for stale data (connection issues)
                    lag = data['meta']['lag_seconds']
                    
                    if lag > max_lag_seconds:
                        stale_count += 1
                        logger.warning(f"Stale data: Lag={lag}s (count: {stale_count})")
                        
                        # Send warning to client
                        data['meta']['stale_warning'] = True
                        data['meta']['stale_message'] = f"Connection may be lost. Data is {lag:.0f} seconds old."
                        
                        if stale_count >= max_stale_before_warning:
                            data['meta']['stale_critical'] = True
                            data['meta']['stale_message'] = "Base station connection lost. Try refreshing the page or checking your Owlet device."
                    else:
                        # Reset counter when fresh data arrives
                        if stale_count > 0:
                            logger.info(f"Fresh data received, lag back to {lag}s")
                        stale_count = 0
                    
                    # Send processed data to the WebSocket client
                    await ws.send_json(data)
                    
                    # Log data to CSV file for historical tracking
                    log_data_to_csv(LOG_FILE, data['vitals'], lag)
                    
                    # Log key vitals to console for monitoring
                    logger.info(
                        f"HR: {data['vitals'].get('hr')} | "
                        f"Lag: {lag}s | "
                        f"BP: {data['vitals'].get('bp')}"
                    )

                # Wait before next update cycle
                await asyncio.sleep(UPDATE_INTERVAL)
                
        except Exception as e:
            logger.error(f"Worker error: {e}")
        finally:
            # Clean up API connection
            await api.close()
    
    return owlet_worker
