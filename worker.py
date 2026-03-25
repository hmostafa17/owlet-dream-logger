"""
Background worker for continuously fetching and streaming Owlet data.

This module contains the main worker loop that authenticates, discovers devices,
fetches vitals data, and streams it via WebSocket while logging to CSV.

Stall Recovery Architecture:
  The Ayla IoT platform requires APP_ACTIVE=1 to be posted periodically as a
  heartbeat. Without it, the base station stops pushing REAL_TIME_VITALS to the
  cloud — alerts still work, but the vitals stream goes stale. pyowletapi's
  activate() has a missing-await bug on re-auth, so token expiry can silently
  kill the heartbeat. This worker implements multi-stage recovery:
    Stage 1 (lag > 30s):  Force re-authenticate + explicit APP_ACTIVE POST
    Stage 2 (lag > 60s):  Full session teardown and rebuild
    Stage 3 (persistent): Back off polling to avoid hammering the API
"""

import asyncio
import time
import logging
import aiohttp
from fastapi import WebSocket

from pyowletapi.api import OwletAPI
from pyowletapi.sock import Sock

from config import UPDATE_INTERVAL, LOG_FILE
from owlet_service import discover_socks
from data_processing import process_properties, find_sleep_start, set_sleep_start
from csv_logger import init_csv_logging, log_data_to_csv

logger = logging.getLogger(__name__)

# Stall recovery thresholds
STALE_LAG_THRESHOLD = 30       # seconds before data is considered stale
RECOVERY_STAGE1_COUNT = 5      # stale cycles before stage 1 (force re-auth)
RECOVERY_STAGE2_COUNT = 15     # stale cycles before stage 2 (full rebuild)
KEEPALIVE_INTERVAL = 25        # seconds between explicit APP_ACTIVE heartbeats


async def _force_activate(api: OwletAPI, serial: str):
    """Explicitly POST APP_ACTIVE=1 to keep the base station streaming vitals.
    Works around the missing-await bug in pyowletapi's activate()."""
    try:
        # Ensure token is fresh before sending heartbeat
        if api._expiry <= time.time():
            logger.info("Token expired, forcing re-authentication before activate")
            await api.authenticate()

        data = {"datapoint": {"metadata": {}, "value": 1}}
        await api.request(
            "POST",
            f"/dsns/{serial}/properties/APP_ACTIVE/datapoints.json",
            data=data,
        )
        logger.debug(f"APP_ACTIVE heartbeat sent for {serial}")
    except Exception as e:
        logger.warning(f"APP_ACTIVE heartbeat failed: {e}")


async def _rebuild_session(email: str, password: str, region: str, old_api: OwletAPI):
    """Tear down old API session and create a fresh one from scratch."""
    try:
        await old_api.close()
    except Exception:
        pass
    logger.info("Rebuilding API session from scratch")
    new_api = OwletAPI(region, email, password)
    await new_api.authenticate()
    return new_api


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
        
        Implements a multi-stage stall recovery system to maintain the vitals
        stream even when the Ayla cloud heartbeat is disrupted.
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
            serial = sock.serial
            
            # Track stale data to detect connection issues
            stale_count = 0
            recovery_stage = 0  # 0=normal, 1=re-auth, 2=rebuild
            last_keepalive = time.time()
            sleep_start_checked = False  # one-time check for in-progress sleep
            
            # Main monitoring loop - runs continuously until connection is closed
            while True:
                try:
                    # --- Proactive keepalive ---
                    # Send APP_ACTIVE heartbeat every KEEPALIVE_INTERVAL seconds
                    # independently of the data fetch cycle, to prevent stalls
                    now = time.time()
                    if now - last_keepalive >= KEEPALIVE_INTERVAL:
                        await _force_activate(api, serial)
                        last_keepalive = now

                    # Fetch latest properties from the sock device
                    result = await asyncio.wait_for(
                        sock.update_properties(),
                        timeout=15  # Don't let a single fetch hang forever
                    )

                    # Handle token refresh
                    if isinstance(result, dict) and "tokens" in result:
                        tokens = result["tokens"]
                        if tokens:
                            logger.info("API tokens refreshed automatically")

                except asyncio.TimeoutError:
                    logger.warning("update_properties() timed out after 15s")
                    stale_count += 1
                    if sock.raw_properties:
                        data = process_properties(sock.raw_properties)
                        data['meta']['stale_warning'] = True
                        data['meta']['stale_message'] = "API call timed out. Attempting recovery..."
                        await ws.send_json(data)
                    await asyncio.sleep(UPDATE_INTERVAL)
                    continue
                except Exception as fetch_err:
                    logger.warning(f"Fetch error: {fetch_err}")
                    stale_count += 1
                    await asyncio.sleep(UPDATE_INTERVAL)
                    continue

                if sock.raw_properties:
                    # Process raw data into structured format
                    data = process_properties(sock.raw_properties)

                    # One-time startup check: if baby is already sleeping,
                    # query datapoint history to find when sleep started
                    if not sleep_start_checked:
                        sleep_start_checked = True
                        if data['meta'].get('sleeping') and not data['meta'].get('sleep_session', {}).get('active'):
                            try:
                                start_ts = await find_sleep_start(api, serial)
                                if start_ts:
                                    set_sleep_start(start_ts)
                                    logger.info(f"Sleep start seeded from datapoint history: {start_ts}")
                                    # Re-process to get updated sleep_session_seconds
                                    data = process_properties(sock.raw_properties)
                            except Exception as e:
                                logger.warning(f"Sleep start lookup failed: {e}")
                    
                    # Check for stale data (connection issues)
                    lag = data['meta']['lag_seconds']
                    
                    if lag > STALE_LAG_THRESHOLD:
                        stale_count += 1
                        logger.warning(f"Stale data: Lag={lag}s (count: {stale_count}, stage: {recovery_stage})")
                        
                        # --- STAGE 1: Force re-auth + explicit APP_ACTIVE ---
                        if stale_count >= RECOVERY_STAGE1_COUNT and recovery_stage < 1:
                            recovery_stage = 1
                            logger.info("RECOVERY STAGE 1: Forcing re-authentication and APP_ACTIVE")
                            try:
                                api._expiry = 0  # Force token refresh
                                await api.authenticate()
                                await _force_activate(api, serial)
                                last_keepalive = time.time()
                            except Exception as e:
                                logger.error(f"Stage 1 recovery failed: {e}")
                            data['meta']['stale_warning'] = True
                            data['meta']['stale_message'] = f"Recovering... Re-authenticated. Data is {lag:.0f}s old."

                        # --- STAGE 2: Full session rebuild ---
                        elif stale_count >= RECOVERY_STAGE2_COUNT and recovery_stage < 2:
                            recovery_stage = 2
                            logger.info("RECOVERY STAGE 2: Full session rebuild")
                            try:
                                api = await _rebuild_session(email, password, region, api)
                                # Re-discover the sock with new API session
                                new_socks = await discover_socks(api)
                                if new_socks:
                                    sock = new_socks[0]
                                    serial = sock.serial
                                else:
                                    all_devs = await api.get_devices()
                                    devices_list = all_devs if isinstance(all_devs, list) else all_devs.get("response", [])
                                    if devices_list:
                                        first_dev = devices_list[0].get("device")
                                        if first_dev:
                                            sock = Sock(api, first_dev)
                                            serial = sock.serial
                                await _force_activate(api, serial)
                                last_keepalive = time.time()
                            except Exception as e:
                                logger.error(f"Stage 2 recovery failed: {e}")
                            data['meta']['stale_warning'] = True
                            data['meta']['stale_critical'] = True
                            data['meta']['stale_message'] = f"Session rebuilt. Waiting for fresh data... ({lag:.0f}s stale)"

                        else:
                            # Ongoing stale - show appropriate warning
                            data['meta']['stale_warning'] = True
                            if stale_count >= RECOVERY_STAGE2_COUNT:
                                data['meta']['stale_critical'] = True
                                data['meta']['stale_message'] = f"Recovery in progress. Data is {lag:.0f}s old. If this persists, check your base station WiFi."
                            else:
                                data['meta']['stale_message'] = f"Connection may be lost. Data is {lag:.0f}s old."
                    else:
                        # Fresh data - reset all recovery state
                        if stale_count > 0:
                            logger.info(f"Fresh data received after {stale_count} stale cycles (stage {recovery_stage}). Lag: {lag}s")
                        stale_count = 0
                        recovery_stage = 0
                    
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
                # Back off slightly during recovery to avoid hammering the API
                sleep_time = UPDATE_INTERVAL
                if recovery_stage >= 2:
                    sleep_time = max(UPDATE_INTERVAL, 5)  # slow to 5s during stage 2
                await asyncio.sleep(sleep_time)
                
        except Exception as e:
            logger.error(f"Worker error: {e}")
        finally:
            # Clean up API connection
            await api.close()
    
    return owlet_worker
