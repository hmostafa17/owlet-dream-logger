"""
Core monitoring loop for Owlet Smart Sock 3.

Shared between the web app (worker.py) and desktop app (desktop_app.py).
Provides an async generator that yields processed vitals data dicts,
handling authentication, device discovery, stall recovery, sleep session
tracking, and proactive keepalive.

Usage:
    async for data in owlet_data_stream(email, password, region, stop_check):
        # data is a dict with vitals, alerts, meta, etc.
        do_something(data)
"""

import asyncio
import time
import logging

from pyowletapi.api import OwletAPI
from pyowletapi.sock import Sock

from config import UPDATE_INTERVAL, LOG_FILE
from owlet_service import discover_socks
from data_processing import process_properties, find_sleep_start, set_sleep_start
from csv_logger import init_csv_logging, log_data_to_csv
from worker import (
    _force_activate,
    _force_base_on,
    _nuke_connection,
    _rebuild_session,
    _parallel_fetch,
    STALE_LAG_THRESHOLD,
    RECOVERY_STAGE1_COUNT,
    RECOVERY_STAGE2_COUNT,
    RECOVERY_RETRY_COUNT,
    KEEPALIVE_INTERVAL,
    PROACTIVE_REFRESH,
)

logger = logging.getLogger(__name__)

# Frozen-stream detection: if vitals haven't changed for this many seconds,
# force hard recovery even though timestamps look fresh.
FROZEN_STREAM_THRESHOLD = 90   # seconds of identical HR+O2 before forced recovery
DEVICE_STUCK_THRESHOLD = 300   # seconds without real vitals change → human intervention needed


def _is_same_vitals(a: dict | None, b: dict | None) -> bool:
    """Compare only core vitals (HR + O2) between two data dicts.
    Ignores timestamps, meta, and other fields that change even when
    the actual vitals stream is frozen."""
    if a is None or b is None:
        return False
    va, vb = a.get("vitals", {}), b.get("vitals", {})
    return va.get("hr") == vb.get("hr") and va.get("o2") == vb.get("o2")


async def _discover_device(api):
    """Discover the first Owlet sock on the account. Returns (sock, serial) or raises."""
    socks = await discover_socks(api)
    if not socks:
        all_devs = await api.get_devices()
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
        raise RuntimeError("No Owlet sock found on this account")
    return socks[0], socks[0].serial


async def owlet_data_stream(email: str, password: str, region: str,
                            stop_check=None):
    """Async generator that yields processed Owlet vitals data dicts.

    Args:
        email: Owlet account email
        password: Owlet account password
        region: API region (e.g. 'world', 'europe')
        stop_check: Optional callable returning True to stop the loop.
                    If None, runs forever.

    Yields:
        dict with keys: vitals, alerts, alarm_priority, device_state,
        all_properties, device_info, alert_history, meta
    """
    init_csv_logging(LOG_FILE)

    api = OwletAPI(region, email, password)
    try:
        await api.authenticate()
        logger.info("Authenticated successfully")

        sock, serial = await _discover_device(api)
        logger.info(f"Monitoring device {serial}")

        stale_count = 0
        recovery_stage = 0
        last_keepalive = time.time()
        fresh_start_time = None
        sleep_start_checked = False
        last_data = None                       # previous yielded data dict
        last_real_change_time = time.time()    # wall-clock of last actual vitals change
        backoff = UPDATE_INTERVAL              # exponential backoff (resets on fresh data)

        while True:
            if stop_check and stop_check():
                break

            try:
                # --- Proactive keepalive (adaptive: faster during degradation) ---
                now = time.time()
                keepalive_interval = KEEPALIVE_INTERVAL
                if stale_count > 0 or recovery_stage > 0:
                    keepalive_interval = 10  # aggressive during recovery
                if now - last_keepalive >= keepalive_interval:
                    await _force_activate(api, serial)
                    last_keepalive = now

                # Fetch via parallel polling (sock + raw API)
                await _parallel_fetch(sock, api, serial)

            except asyncio.TimeoutError:
                logger.warning("Parallel fetch timed out after 15s")
                stale_count = min(stale_count + 1, 20)
                last_keepalive = time.time()
                if sock.raw_properties:
                    data = process_properties(sock.raw_properties)
                    data['meta']['stale_warning'] = True
                    data['meta']['stale_message'] = "API call timed out. Attempting recovery..."
                    yield data
                await asyncio.sleep(UPDATE_INTERVAL)
                continue
            except Exception as fetch_err:
                logger.warning(f"Fetch error: {fetch_err}")
                stale_count = min(stale_count + 1, 20)
                last_keepalive = time.time()
                await asyncio.sleep(UPDATE_INTERVAL)
                continue

            if not sock.raw_properties:
                await asyncio.sleep(UPDATE_INTERVAL)
                continue

            data = process_properties(sock.raw_properties)

            # --- One-time sleep session recovery from history ---
            if not sleep_start_checked:
                sleep_start_checked = True
                chg_now = data['vitals'].get('chg', 0)
                if chg_now not in (1, 2) and not data['meta'].get('sleep_session', {}).get('active'):
                    try:
                        start_info = await find_sleep_start(api, serial)
                        if start_info:
                            set_sleep_start(start_info)
                            logger.info(
                                f"Sleep start seeded from history: start={start_info['start_ts']}, "
                                f"light={start_info['light_secs']:.0f}s, "
                                f"deep={start_info['deep_secs']:.0f}s, "
                                f"awake={start_info['awake_secs']:.0f}s"
                            )
                            data = process_properties(sock.raw_properties)
                        else:
                            logger.info("No active sleep session found in history")
                    except Exception as e:
                        logger.warning(f"Sleep start lookup failed: {e}")

            # --- Null vitals detection (critical failure state) ---
            hr = data['vitals'].get('hr')
            o2 = data['vitals'].get('o2')
            if hr is None or o2 is None:
                stale_count = min(stale_count + 2, 20)  # stronger penalty, capped
                logger.warning(f"Null vitals: hr={hr}, o2={o2} (stale_count={stale_count})")
                data['meta']['stale_warning'] = True
                data['meta']['stale_message'] = "No vitals data from device."
                yield data
                await asyncio.sleep(UPDATE_INTERVAL)
                continue

            # --- Frozen stream detection (vitals unchanged but timestamps look fresh) ---
            now = time.time()
            if _is_same_vitals(last_data, data):
                time_since_real_change = now - last_real_change_time
                if time_since_real_change > FROZEN_STREAM_THRESHOLD:
                    logger.warning(
                        f"Frozen stream detected: HR={hr} O2={o2} unchanged for "
                        f"{time_since_real_change:.0f}s — forcing hard recovery"
                    )
                    stale_count = RECOVERY_STAGE2_COUNT  # jump straight to stage 2
                    data['meta']['stale_warning'] = True
                    data['meta']['stale_critical'] = True
                    data['meta']['stale_message'] = (
                        f"Vitals frozen for {time_since_real_change:.0f}s. Recovering..."
                    )
            else:
                last_real_change_time = now

            last_data = data

            # --- Device stuck detection (human intervention required) ---
            time_stuck = time.time() - last_real_change_time
            if recovery_stage >= 2 and time_stuck > DEVICE_STUCK_THRESHOLD:
                logger.critical(
                    f"DEVICE STUCK: vitals unchanged for {time_stuck:.0f}s across multiple "
                    f"recovery attempts. Manual base station restart may be required."
                )
                data['meta']['stale_warning'] = True
                data['meta']['stale_critical'] = True
                data['meta']['device_stuck'] = True
                data['meta']['stale_message'] = (
                    f"Device unresponsive for {time_stuck:.0f}s. "
                    f"Try unplugging the base station for 10 seconds."
                )

            # --- Stale data detection + recovery ---
            lag = data['meta']['lag_seconds']

            if lag > STALE_LAG_THRESHOLD or stale_count >= RECOVERY_STAGE2_COUNT:
                stale_count = min(stale_count + 1, 20)  # cap to prevent runaway inflation
                fresh_start_time = None
                logger.warning(f"Stale data: Lag={lag}s (count: {stale_count}, stage: {recovery_stage})")

                # STAGE 1: Force re-auth + APP_ACTIVE toggle
                if stale_count >= RECOVERY_STAGE1_COUNT and recovery_stage < 1:
                    recovery_stage = 1
                    logger.info("RECOVERY STAGE 1: Re-auth + APP_ACTIVE toggle + BASE_STATION_ON")
                    try:
                        api._expiry = 0
                        await api.authenticate()
                        await _force_activate(api, serial, toggle=True)
                        await _force_base_on(api, serial)
                        last_keepalive = time.time()
                    except Exception as e:
                        logger.error(f"Stage 1 recovery failed: {e}")
                    data['meta']['stale_warning'] = True
                    data['meta']['stale_message'] = (
                        f"Recovering... Re-authenticated + base station on. Data is {lag:.0f}s old."
                    )

                # STAGE 2: Full session rebuild + device kick
                elif stale_count >= RECOVERY_STAGE2_COUNT and recovery_stage < 2:
                    recovery_stage = 2
                    logger.info("RECOVERY STAGE 2: Nuke + full session rebuild + device kick")
                    try:
                        await _nuke_connection(api, serial)
                        api, sock, serial = await _rebuild_session(email, password, region, api)
                        last_keepalive = time.time()
                    except Exception as e:
                        logger.error(f"Stage 2 recovery failed: {e}")
                    data['meta']['stale_warning'] = True
                    data['meta']['stale_critical'] = True
                    data['meta']['stale_message'] = (
                        f"Session rebuilt + device kick. Waiting for fresh data... ({lag:.0f}s stale)"
                    )

                else:
                    # Ongoing stale
                    data['meta']['stale_warning'] = True
                    if stale_count >= RECOVERY_STAGE2_COUNT:
                        data['meta']['stale_critical'] = True
                        # Periodic full retry with exponential backoff
                        if recovery_stage >= 2 and stale_count >= RECOVERY_STAGE2_COUNT + RECOVERY_RETRY_COUNT:
                            logger.info(f"Recovery retry: full rebuild after {stale_count} stale cycles (backoff={backoff}s)")
                            await asyncio.sleep(backoff)
                            backoff = min(backoff * 2, 60)
                            try:
                                await _nuke_connection(api, serial)
                                api, sock, serial = await _rebuild_session(email, password, region, api)
                                last_keepalive = time.time()
                            except Exception as e:
                                logger.error(f"Recovery retry failed: {e}")
                            # Full state reset after recovery attempt
                            stale_count = 0
                            recovery_stage = 0
                            fresh_start_time = None
                            last_data = None
                            last_real_change_time = time.time()
                            data['meta']['stale_message'] = f"Connection nuked, retrying... Data is {lag:.0f}s old."
                        else:
                            data['meta']['stale_message'] = f"Recovery in progress. Data is {lag:.0f}s old."
                    else:
                        data['meta']['stale_message'] = f"Connection may be lost. Data is {lag:.0f}s old."
            else:
                # Fresh data - full state reset
                if stale_count > 0:
                    logger.info(
                        f"Fresh data received after {stale_count} stale cycles (stage {recovery_stage}). Lag: {lag}s"
                    )
                stale_count = 0
                recovery_stage = 0
                backoff = UPDATE_INTERVAL  # reset exponential backoff on success

                # --- Proactive refresh ---
                if fresh_start_time is None:
                    fresh_start_time = time.time()
                elif time.time() - fresh_start_time >= PROACTIVE_REFRESH:
                    logger.info(
                        f"Proactive refresh: APP_ACTIVE toggle after "
                        f"{time.time() - fresh_start_time:.0f}s of fresh data"
                    )
                    try:
                        await _force_activate(api, serial, toggle=True)
                        last_keepalive = time.time()
                    except Exception as e:
                        logger.warning(f"Proactive refresh failed: {e}")
                    fresh_start_time = time.time()

            # Yield data to consumer
            yield data

            # Log to CSV
            log_data_to_csv(LOG_FILE, data['vitals'], lag)

            logger.info(
                f"HR: {data['vitals'].get('hr')} | "
                f"O2: {data['vitals'].get('o2')} | "
                f"Lag: {lag}s | "
                f"BP: {data['vitals'].get('bp')}"
            )

            # Back off during recovery (exponential)
            sleep_time = UPDATE_INTERVAL
            if recovery_stage >= 2:
                sleep_time = backoff
            await asyncio.sleep(sleep_time)

    except Exception as e:
        logger.error(f"Monitor error: {e}")
        raise
    finally:
        await api.close()
