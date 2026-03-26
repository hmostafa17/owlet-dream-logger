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
    Retry:                After prolonged stall, restart recovery pipeline
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
RECOVERY_STAGE1_COUNT = 1      # stale cycles before stage 1 (immediate)
RECOVERY_STAGE2_COUNT = 5      # stale cycles before stage 2 (nuke)
RECOVERY_RETRY_COUNT = 8       # stale cycles after stage 2 before retrying
KEEPALIVE_INTERVAL = 15        # seconds between explicit APP_ACTIVE heartbeats
PROACTIVE_REFRESH = 15         # seconds of continuous fresh data before proactive activate


async def _force_activate(api: OwletAPI, serial: str, toggle: bool = False):
    """Explicitly POST APP_ACTIVE to keep the base station streaming vitals.
    Works around the missing-await bug in pyowletapi's activate().

    Args:
        toggle: If True, send APP_ACTIVE=0 first then APP_ACTIVE=1.
                This can force the Ayla cloud to re-queue the command,
                improving the chance the base station picks it up when
                its push channel has dropped.
    """
    try:
        # Ensure token is fresh before sending heartbeat
        if api._expiry <= time.time():
            logger.info("Token expired, forcing re-authentication before activate")
            await api.authenticate()

        endpoint = f"/dsns/{serial}/properties/APP_ACTIVE/datapoints.json"

        if toggle:
            off = {"datapoint": {"metadata": {}, "value": 0}}
            await api.request("POST", endpoint, data=off)
            logger.debug(f"APP_ACTIVE toggled OFF for {serial}")
            await asyncio.sleep(1)

        on = {"datapoint": {"metadata": {}, "value": 1}}
        await api.request("POST", endpoint, data=on)
        logger.debug(f"APP_ACTIVE heartbeat sent for {serial} (toggle={toggle})")
    except Exception as e:
        logger.warning(f"APP_ACTIVE heartbeat failed: {e}")


async def _force_base_on(api: OwletAPI, serial: str):
    """Command the base station to turn on via BASE_STATION_ON_CMD.
    The Ayla property accepts a JSON string with a timestamp and val='true'.
    If the base was previously told to turn off (val='false'), it will stay
    off even if APP_ACTIVE=1 is being sent — vitals won't stream."""
    try:
        if api._expiry <= time.time():
            await api.authenticate()

        import json as _json
        ts = int(time.time())
        cmd = _json.dumps({"ts": ts, "val": "true"})
        data = {"datapoint": {"metadata": {}, "value": cmd}}
        await api.request(
            "POST",
            f"/dsns/{serial}/properties/BASE_STATION_ON_CMD/datapoints.json",
            data=data,
        )
        logger.info(f"BASE_STATION_ON_CMD sent for {serial} (ts={ts})")
    except Exception as e:
        logger.warning(f"BASE_STATION_ON_CMD failed: {e}")


async def _device_ping(api: OwletAPI, serial: str):
    """Send DEVICE_PING to try to force the base station to check in.
    This may nudge the Ayla cloud to re-establish the push channel."""
    try:
        if api._expiry <= time.time():
            await api.authenticate()

        data = {"datapoint": {"metadata": {}, "value": 1}}
        await api.request(
            "POST",
            f"/dsns/{serial}/properties/DEVICE_PING/datapoints.json",
            data=data,
        )
        logger.info(f"DEVICE_PING sent for {serial}")
    except Exception as e:
        logger.warning(f"DEVICE_PING failed: {e}")


async def _nuke_connection(api: OwletAPI, serial: str):
    """Force the BASE STATION to drop its cloud connection and re-establish it.
    Tears down the local HTTP session, re-authenticates, and toggles base station
    off/on via cloud commands to force a fresh TCP connection to the Ayla cloud.
    """
    import json as _json
    
    try:
        # Step 1: Kill our TCP connection pool
        old_session = api.session
        if old_session and not old_session.closed:
            connector = old_session.connector
            if connector:
                await connector.close()
                logger.info("Closed aiohttp connector (TCP pool destroyed)")
            await old_session.close()
            logger.info("Closed aiohttp session")

        # Step 2: Create fresh session with new connector (no connection reuse)
        new_connector = aiohttp.TCPConnector(
            force_close=True,
            enable_cleanup_closed=True,
        )
        api.session = aiohttp.ClientSession(
            raise_for_status=True,
            connector=new_connector,
        )
        logger.info("Created fresh aiohttp session with new TCP connector")

        # Step 3: Force re-authenticate (new TLS handshake)
        api._auth_token = None
        api._expiry = 0
        await api.authenticate()
        logger.info("Re-authenticated with fresh connection")

        endpoint_base = f"/dsns/{serial}/properties/BASE_STATION_ON_CMD/datapoints.json"
        endpoint_lpm = f"/dsns/{serial}/properties/LOW_POWER_MODE_CMD/datapoints.json"

        # Step 4: Command base station OFF
        ts = int(time.time())
        off_cmd = _json.dumps({"ts": ts, "val": "false"})
        await api.request("POST", endpoint_base, data={"datapoint": {"metadata": {}, "value": off_cmd}})
        logger.info(f"BASE_STATION_ON_CMD OFF sent for {serial}")

        # Step 5: Force low-power mode (drops base station's TCP to Ayla cloud)
        try:
            await api.request("POST", endpoint_lpm, data={"datapoint": {"metadata": {}, "value": 1}})
            logger.info(f"LOW_POWER_MODE_CMD=1 sent for {serial}")
        except Exception as e:
            logger.warning(f"LOW_POWER_MODE_CMD=1 failed (may not be supported): {e}")

        # Step 6: Wait for base station to fully tear down its cloud connection
        logger.info("Waiting 10 seconds for base station to drop cloud connection...")
        await asyncio.sleep(10)

        # Step 7: Exit low-power mode
        try:
            await api.request("POST", endpoint_lpm, data={"datapoint": {"metadata": {}, "value": 0}})
            logger.info(f"LOW_POWER_MODE_CMD=0 sent for {serial}")
        except Exception as e:
            logger.warning(f"LOW_POWER_MODE_CMD=0 failed: {e}")

        # Step 8: Command base station ON (forces reconnect to Ayla cloud)
        ts2 = int(time.time())
        on_cmd = _json.dumps({"ts": ts2, "val": "true"})
        await api.request("POST", endpoint_base, data={"datapoint": {"metadata": {}, "value": on_cmd}})
        logger.info(f"BASE_STATION_ON_CMD ON sent for {serial}")

        # Step 9: Wait a moment then kick the push channel
        await asyncio.sleep(3)
        await _force_activate(api, serial, toggle=True)
        await _device_ping(api, serial)

        logger.info("Connection nuke complete (LAN + cloud) - base station should be reconnecting")
    except Exception as e:
        logger.error(f"Connection nuke failed: {e}")


def _patch_activate():
    """Monkey-patch pyowletapi's OwletAPI to:
    1. Fix the missing-await bug in activate() on re-authentication.
    2. Throttle activate() inside get_properties() to once every ~5 seconds
       instead of every poll (every 2s = 30/min overwhelmed the Ayla cloud).
       Removing it entirely caused the base station to drop its push channel
       after ~36 seconds. Throttling to ~5s keeps the channel alive without
       spamming."""

    _last_activate_time = [0.0]  # mutable container for closure
    ACTIVATE_THROTTLE = 5        # seconds between activate() calls inside get_properties

    async def _fixed_activate(self, device_serial: str) -> None:
        if self._expiry <= time.time():
            await self.authenticate()  # Fixed: was self.authenticate() without await
        data = {"datapoint": {"metadata": {}, "value": 1}}
        await self.request(
            "POST",
            f"/dsns/{device_serial}/properties/APP_ACTIVE/datapoints.json",
            data=data,
        )

    async def _get_properties_throttled(self, device: str):
        """Fetch device properties with THROTTLED activate() calls.
        activate() is called at most once every ACTIVATE_THROTTLE seconds
        instead of on every poll. This keeps the Ayla push channel alive
        without overwhelming the cloud (was 30/min, now ~12/min)."""
        if self._expiry <= time.time():
            await self.authenticate()

        now = time.time()
        if now - _last_activate_time[0] >= ACTIVATE_THROTTLE:
            await _fixed_activate(self, device)
            _last_activate_time[0] = now
            logger.debug(f"Throttled activate sent for {device} (interval={ACTIVATE_THROTTLE}s)")

        response = await self.request("GET", f"/dsns/{device}/properties.json")
        properties = {}
        for prop in response:
            properties[prop["property"]["name"]] = prop["property"]
        return properties

    OwletAPI.activate = _fixed_activate
    OwletAPI.get_properties = _get_properties_throttled
    logger.info("Patched pyowletapi: fixed activate() await bug + throttled activate to every 5s")

_patch_activate()


async def _rebuild_session(email: str, password: str, region: str, old_api: OwletAPI):
    """Tear down old API session, create a fresh one, re-subscribe to the device,
    and run the 'device kick' sequence that the official Owlet app performs on reconnect.

    Returns (new_api, new_sock, serial).
    """
    try:
        await old_api.close()
    except Exception:
        pass
    logger.info("Rebuilding API session from scratch")

    # 1. Fresh API + auth
    new_api = OwletAPI(region, email, password)
    await new_api.authenticate()
    logger.info("Re-authenticated with fresh API session")

    # 2. Full device re-subscription (new Sock object)
    new_socks = await discover_socks(new_api)
    if not new_socks:
        all_devs = await new_api.get_devices()
        devices_list = all_devs if isinstance(all_devs, list) else all_devs.get("response", [])
        if devices_list:
            first_dev = devices_list[0].get("device")
            if first_dev:
                new_socks = [Sock(new_api, first_dev)]
    if not new_socks:
        raise RuntimeError("No device found after session rebuild")

    new_sock = new_socks[0]
    serial = new_sock.serial
    logger.info(f"Re-subscribed to device {serial}")

    # 3. Device kick sequence (mimics official Owlet app reconnect)
    try:
        await new_sock.update_properties()
        logger.debug("Kick step 1: initial update_properties OK")
        await asyncio.sleep(2)
        await _force_activate(new_api, serial)
        logger.debug("Kick step 2: APP_ACTIVE sent")
        await asyncio.sleep(2)
        await new_sock.update_properties()
        logger.debug("Kick step 3: second update_properties OK")
    except Exception as e:
        logger.warning(f"Device kick sequence partially failed: {e}")

    return new_api, new_sock, serial


async def _parallel_fetch(sock, api, serial):
    """Fetch properties via both the Sock object AND a raw API GET in parallel.
    The Sock.update_properties() uses pyowletapi's internal caching/subscription
    layer, while the raw endpoint hits Ayla directly. Whichever returns first
    ensures we get the freshest data; both populate sock.raw_properties."""
    async def _raw_fetch():
        resp = await api.request("GET", f"/dsns/{serial}/properties.json")
        props = {}
        for prop in resp:
            props[prop["property"]["name"]] = prop["property"]
        return props

    # Run both in parallel, wait for both (up to 15s total)
    sock_task = asyncio.create_task(sock.update_properties())
    raw_task = asyncio.create_task(_raw_fetch())

    done, pending = await asyncio.wait(
        [sock_task, raw_task],
        timeout=15,
        return_when=asyncio.ALL_COMPLETED,
    )

    # Collect raw fetch result
    raw_props = None
    if raw_task in done:
        try:
            raw_props = raw_task.result()
        except Exception:
            pass

    # Cancel anything still running
    for t in pending:
        if not t.done():
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass

    # If raw fetch got data and sock didn't update, inject it
    if raw_props and not sock.raw_properties:
        sock.raw_properties = raw_props
    elif raw_props and sock.raw_properties:
        # Merge: use whichever has a more recent REAL_TIME_VITALS timestamp
        raw_ts = raw_props.get("REAL_TIME_VITALS", {}).get("data_updated_at", "")
        sock_ts = sock.raw_properties.get("REAL_TIME_VITALS", {}).get("data_updated_at", "")
        if raw_ts > sock_ts:
            sock.raw_properties = raw_props
            logger.debug("Using raw API data (fresher than sock)")


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
        """Thin wrapper: streams data from owlet_monitor to a WebSocket client."""
        from owlet_monitor import owlet_data_stream

        try:
            async for data in owlet_data_stream(email, password, region):
                await ws.send_json(data)
        except Exception as e:
            logger.error(f"Worker error: {e}")
    
    return owlet_worker
