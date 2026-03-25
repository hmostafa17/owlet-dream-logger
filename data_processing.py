"""
Data processing utilities for Owlet device properties and vitals.

This module handles parsing, transforming, and structuring raw device data
from the Owlet API into a format suitable for display and logging.
"""

import base64
import json
from datetime import datetime, timezone


# --- Sleep session tracking (persists across calls) ---
# A session starts when ss first enters 8 or 15, and only ends when
# the sock is docked (chg==1 or chg==2).  Brief awakenings during the
# session are normal and do NOT close the session.
_sleep_session = {
    "active": False,     # whether a session is in progress
    "start_ts": None,    # Unix epoch when session began (server-side)
    "last_ts": None,     # Unix epoch of last processed reading
    "last_ss": None,     # previous ss value
    "light_secs": 0.0,   # accumulated seconds in Light Sleep (ss=8)
    "deep_secs": 0.0,    # accumulated seconds in Deep Sleep (ss=15)
    "awake_secs": 0.0,   # accumulated seconds awake *during* session (ss=1)
}


def set_sleep_start(epoch: float):
    """Seed the sleep session from an external source (e.g. datapoint history)."""
    _sleep_session["active"] = True
    _sleep_session["start_ts"] = epoch
    # We don't know state breakdown from history, so leave counters at 0;
    # they'll accumulate from this point on.
    _sleep_session["last_ts"] = epoch


def reset_sleep_session():
    """Close the current sleep session (called when sock is docked)."""
    _sleep_session["active"] = False
    _sleep_session["start_ts"] = None
    _sleep_session["last_ts"] = None
    _sleep_session["last_ss"] = None
    _sleep_session["light_secs"] = 0.0
    _sleep_session["deep_secs"] = 0.0
    _sleep_session["awake_secs"] = 0.0


async def find_sleep_start(api, dsn: str) -> float | None:
    """Query Ayla datapoint history to find when the current sleep session began.

    Walks backwards through recent REAL_TIME_VITALS datapoints looking for
    the earliest consecutive sleeping reading (not interrupted by docking).

    Returns the Unix epoch of the sleep start, or None if not found.
    """
    try:
        resp = await api.request(
            "GET",
            f"/dsns/{dsn}/properties/REAL_TIME_VITALS/datapoints.json?limit=500&order=desc",
        )
    except Exception:
        return None

    if not isinstance(resp, list) or not resp:
        return None

    # Walk from most recent backwards; find where the session started.
    # The session boundary is a docking event (chg==1 or chg==2) or
    # reaching the end of available history.
    last_sleep_ts = None
    for dp in resp:
        d = dp.get("datapoint", dp)
        val = d.get("value", "")
        try:
            v = json.loads(val) if isinstance(val, str) else val
        except Exception:
            continue
        if not isinstance(v, dict):
            continue

        ss = v.get("ss")
        chg = v.get("chg", 0)

        ts_str = d.get("updated_at") or d.get("created_at")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
        except Exception:
            continue

        # If we hit a docking event, the session started after this point
        if chg in (1, 2):
            break

        if ss in (8, 15):
            last_sleep_ts = ts  # keep going further back
        # ss=1 (awake) during session is fine — keep walking

    return last_sleep_ts


def robust_json_parse(value):
    """
    Safely parse JSON strings into Python objects.
    
    Args:
        value: String or other value that might contain JSON
        
    Returns:
        Parsed JSON object or original value if parsing fails
    """
    if isinstance(value, str):
        value = value.strip()
        if value.startswith("{") or value.startswith("["):
            try:
                return json.loads(value)
            except:
                return value
    return value


def _decode_alert_history(raw_props):
    """Decode RED_ALERT_SUMMARY base64 field into alert event records.
    Returns dict with 'records' list, 'updated_at' (property timestamp), and 'header_epoch' (if decodable).
    """
    ALERT_TYPE_NAMES = {
        1: "Low Oxygen", 2: "Critical Oxygen", 3: "Low HR",
        4: "High HR", 5: "Critical Battery", 6: "General",
        7: "Sock Off", 8: "Sock Disconnected",
    }
    empty = {"records": [], "updated_at": None, "header_epoch": None}
    if "RED_ALERT_SUMMARY" not in raw_props:
        return empty
    prop = raw_props["RED_ALERT_SUMMARY"]
    updated_at = prop.get("data_updated_at") if isinstance(prop, dict) else None
    val = prop.get("value") if isinstance(prop, dict) else prop
    if not val or val == "None" or not isinstance(val, str):
        return {**empty, "updated_at": updated_at}
    try:
        padded = str(val) + "=" * (-len(str(val)) % 4)
        decoded = base64.b64decode(padded)
    except Exception:
        return {**empty, "updated_at": updated_at}
    if len(decoded) < 15:
        return {**empty, "updated_at": updated_at}

    # Try to extract a Unix epoch from header bytes 0-3 (big-endian)
    import struct
    header_epoch = None
    if len(decoded) >= 4:
        candidate = struct.unpack(">I", decoded[0:4])[0]
        # Plausible epoch: between 2020-01-01 and 2030-01-01
        if 1577836800 <= candidate <= 1893456000:
            header_epoch = datetime.fromtimestamp(candidate, tz=timezone.utc).isoformat()

    records = []
    i = 10  # skip header
    while i + 5 <= len(decoded):
        hr, ox, duration, alert_type, flags = decoded[i], decoded[i+1], decoded[i+2], decoded[i+3], decoded[i+4]
        i += 5
        if hr == 0 and ox == 0 and duration == 0 and alert_type == 0 and flags == 0:
            continue
        records.append({
            "hr": hr, "ox": ox, "duration": duration,
            "type": alert_type,
            "type_name": ALERT_TYPE_NAMES.get(alert_type, f"Type {alert_type}"),
            "flags": flags,
        })
    return {"records": records, "updated_at": updated_at, "header_epoch": header_epoch}


def _extract_device_info(raw_props):
    """Extract firmware, config, and settings from raw properties."""
    info = {}
    # Firmware
    if "oem_base_version" in raw_props and isinstance(raw_props["oem_base_version"], dict):
        try:
            fw = json.loads(raw_props["oem_base_version"]["value"])
            info["base_fw"] = fw.get("app", "?")
            info["base_hw"] = fw.get("hw", "?")
        except Exception:
            pass
    if "oem_sock_version" in raw_props and isinstance(raw_props["oem_sock_version"], dict):
        try:
            fw = json.loads(raw_props["oem_sock_version"]["value"])
            info["sock_fw"] = fw.get("app", "?")
            info["sock_bl"] = fw.get("bl", "?")
        except Exception:
            pass
    if "oem_flash_version" in raw_props and isinstance(raw_props["oem_flash_version"], dict):
        info["flash_version"] = raw_props["oem_flash_version"].get("value", "?")
    # Config (MACs)
    if "CONFIG_STATUS" in raw_props and isinstance(raw_props["CONFIG_STATUS"], dict):
        try:
            cfg = json.loads(raw_props["CONFIG_STATUS"]["value"])
            info["sock_mac"] = cfg.get("smac", "?")
            info["base_mac"] = cfg.get("bmac", "?")
        except Exception:
            pass
    # Settings
    if "SETTINGS_STATUS" in raw_props and isinstance(raw_props["SETTINGS_STATUS"], dict):
        try:
            settings = json.loads(raw_props["SETTINGS_STATUS"]["value"])
            s = settings.get("settings", {})
            info["onm_setting"] = s.get("onm")
            info["ox_baseline"] = s.get("blox")
            info["hr_baseline"] = s.get("blhr")
            info["sleep_state"] = s.get("sst")
        except Exception:
            pass
    # FW update
    if "FW_UPDATE_STATUS" in raw_props and isinstance(raw_props["FW_UPDATE_STATUS"], dict):
        try:
            fws = json.loads(raw_props["FW_UPDATE_STATUS"]["value"])
            info["fw_update"] = fws.get("primary", "?")
        except Exception:
            pass
    # Battery status
    if "BATTERY_STATUS" in raw_props and isinstance(raw_props["BATTERY_STATUS"], dict):
        info["battery_raw"] = raw_props["BATTERY_STATUS"].get("value")
    return info


def process_properties(raw_props, alerts=None):
    """
    Process raw device properties into structured vitals data and metadata.
    
    Extracts REAL_TIME_VITALS data and calculates data lag to determine freshness.
    
    Args:
        raw_props: Dictionary of raw properties from the Owlet device
        alerts: Optional dict of boolean alert flags from sock.properties
        
    Returns:
        Dictionary containing:
        - vitals: Key vital signs (heart rate, oxygen, movement, etc.)
        - alerts: Active alert flags from the device
        - all_properties: All properties for the inspector table
        - meta: Metadata including data lag in seconds
    """
    vitals = {}
    table_data = []
    last_update_ts = None

    # Extract real-time vitals from the REAL_TIME_VITALS property
    if "REAL_TIME_VITALS" in raw_props:
        prop = raw_props["REAL_TIME_VITALS"]
        
        # Extract the timestamp when this data was last updated
        if prop.get("data_updated_at"):
            try:
                dt = datetime.fromisoformat(prop.get("data_updated_at").replace('Z', '+00:00'))
                last_update_ts = dt.timestamp()
            except:
                pass

        # Parse the JSON value containing all vitals
        d = robust_json_parse(prop.get("value"))
        if isinstance(d, dict):
            # Extract all vital sign measurements into a structured dictionary
            vitals = {
                "hr": d.get("hr"),      # Heart rate in BPM
                "ox": d.get("ox"),      # Oxygen saturation percentage (SpO2)
                "oxta": d.get("oxta"),  # 10-second rolling average SpO2 (255 = no data)
                "mv": d.get("mv"),      # Raw accelerometer movement intensity (0-146+)
                "mvb": d.get("mvb"),    # Movement bucket - normalized 0-100% scale
                "bat": d.get("bat"),    # Battery percentage
                "btt": d.get("btt"),    # Battery time remaining in minutes
                "chg": d.get("chg"),    # Charging status (0=none, 1=charging, 2=charged)
                "rsi": d.get("rsi"),    # WiFi/BLE signal strength indicator
                "ss": d.get("ss"),      # Sleep state (0=inactive, 1=awake, 8=light, 15=deep)
                "sc": d.get("sc"),      # Sock-to-base connection (2=connected)
                "bp": d.get("bp"),      # Band placement state (7=idle, 1=calibrating, 8=stabilizing, 9=acquiring, 10=monitoring, 11=settling, 6=degraded)
                "hw": d.get("hw"),      # Hardware version (e.g. "obs4")
                "bsb": d.get("bsb"),    # Base station battery backup status
                "onm": d.get("onm"),    # Wellness alert / monitoring mode (3=active)
                "bso": d.get("bso"),    # Base station on (1=on, 0=off)
                "mrs": d.get("mrs"),    # Monitoring ready status (1=ready)
                "st": d.get("st"),      # Skin temperature
                "srf": d.get("srf"),    # Sensor readings flag (1=valid readings available)
            }

    # Extract alert flags from raw properties (boolean alerts from API)
    alert_flags = {}
    alert_keys = {
        "LOW_OX_ALRT": "low_oxygen",
        "CRIT_OX_ALRT": "critical_oxygen",
        "LOW_HR_ALRT": "low_heart_rate",
        "HIGH_HR_ALRT": "high_heart_rate",
        "CRIT_BATT_ALRT": "critical_battery",
        "LOW_BATT_ALRT": "low_battery",
        "SOCK_DISCON_ALRT": "sock_disconnected",
        "SOCK_OFF": "sock_off",
        "LOST_POWER_ALRT": "lost_power",
        "DISCOMFORT_ALRT": "discomfort",
        "LOW_INTEG_READ": "low_integrity_read",
    }
    for raw_key, friendly_key in alert_keys.items():
        if raw_key in raw_props and isinstance(raw_props[raw_key], dict):
            val = raw_props[raw_key].get("value")
            if val in (1, True, "1", "true"):
                alert_flags[friendly_key] = True

    # Extract alarm priority levels (PREVIEW_*_PRIORITY_ALARM)
    alarm_priority = None
    for level in ("HIGH", "MED", "LOW"):
        key = f"PREVIEW_{level}_PRIORITY_ALARM"
        if key in raw_props and isinstance(raw_props[key], dict):
            val = raw_props[key].get("value")
            if val in (1, True, "1", "true"):
                alarm_priority = level
                break  # highest active priority wins

    # If normalized alerts from sock.properties are provided, merge them
    if alerts:
        for key in ("low_oxygen_alert", "critical_oxygen_alert", "low_heart_rate_alert",
                     "high_heart_rate_alert", "critical_battery_alert", "low_battery_alert",
                     "sock_disconnected", "sock_off", "lost_power_alert"):
            if alerts.get(key):
                # Convert from property-style to our friendly key
                friendly = key.replace("_alert", "").replace("alert", "")
                alert_flags[friendly] = True

    # Build table data for the property inspector (includes all properties)
    for key, prop in raw_props.items():
        if not isinstance(prop, dict):
            continue
        table_data.append({
            "name": key,
            "display_name": prop.get("display_name", key),
            "value": robust_json_parse(prop.get("value")),
            "updated_at": prop.get("data_updated_at")
        })
    
    # Calculate data lag (time difference between now and last update)
    lag = 0
    if last_update_ts:
        now_ts = datetime.now(timezone.utc).timestamp()
        lag = now_ts - last_update_ts

    # Extract device info and alert history (decoded once per cycle)
    device_info = _extract_device_info(raw_props)
    alert_history = _decode_alert_history(raw_props)

    # --- Compute Device State (jlamendo LIR truth table) ---
    # LOW_INTEG_READ = sock connected but sensor can't get a valid reading (yellow light)
    # Combine with actual HR/SpO2 to determine true state
    lir_flag = alert_flags.get("low_integrity_read", False)
    hr_val = vitals.get("hr", 0) or 0
    ox_val = vitals.get("ox", 0) or 0
    chg_val = vitals.get("chg", 0) or 0
    bso_val = vitals.get("bso", 0) or 0

    # Integrity checks: is each vital reading valid and not flagged?
    bpm_integ = hr_val > 0 and not alert_flags.get("low_heart_rate", False)
    spo2_integ = ox_val > 0 and not alert_flags.get("low_oxygen", False)

    # LIR truth table: if LOW_INTEG_READ is set OR both vitals are zero/flagged
    lir = lir_flag or (not bpm_integ and not spo2_integ)

    # Determine device state — charging takes priority over disconnect detection
    # because when docked, bso=0 and hr/ox=0 (LIR=true) but that's normal.
    if chg_val == 1:
        device_state = "Charging"
    elif chg_val == 2:
        device_state = "Charged"
    elif lir and bso_val != 1:
        device_state = "Disconnected"
    elif lir:
        device_state = "No Signal"
    else:
        device_state = "Monitoring"

    # --- Motion artifact detection ---
    mvb_val = vitals.get("mvb", 0) or 0
    motion_artifact = mvb_val >= 50

    # --- Sleep session tracking ---
    # Session starts when ss first enters 8 or 15.
    # Session ends ONLY when the sock is docked (chg == 1 or 2).
    # Brief awakenings (ss=1) during a session are normal and tracked separately.
    ss_val = vitals.get("ss")
    sleeping = ss_val in (8, 15)
    in_session_awake = ss_val == 1 and _sleep_session["active"]

    # Docking ends the session
    if chg_val in (1, 2) and _sleep_session["active"]:
        reset_sleep_session()

    # Start a new session on first sleep after no session
    if sleeping and not _sleep_session["active"]:
        _sleep_session["active"] = True
        _sleep_session["start_ts"] = last_update_ts
        _sleep_session["last_ts"] = last_update_ts
        _sleep_session["last_ss"] = ss_val
        _sleep_session["light_secs"] = 0.0
        _sleep_session["deep_secs"] = 0.0
        _sleep_session["awake_secs"] = 0.0

    # Accumulate time in current state
    if _sleep_session["active"] and last_update_ts and _sleep_session["last_ts"]:
        delta = last_update_ts - _sleep_session["last_ts"]
        if 0 < delta < 300:  # ignore gaps > 5 min (connection loss)
            prev_ss = _sleep_session["last_ss"]
            if prev_ss == 8:
                _sleep_session["light_secs"] += delta
            elif prev_ss == 15:
                _sleep_session["deep_secs"] += delta
            elif prev_ss == 1:
                _sleep_session["awake_secs"] += delta

    if _sleep_session["active"]:
        _sleep_session["last_ts"] = last_update_ts
        _sleep_session["last_ss"] = ss_val

    # Build sleep meta
    session_active = _sleep_session["active"]
    total_sleep = _sleep_session["light_secs"] + _sleep_session["deep_secs"]
    total_session = total_sleep + _sleep_session["awake_secs"]

    return {
        "vitals": vitals,
        "alerts": alert_flags,
        "alarm_priority": alarm_priority,
        "device_state": device_state,
        "all_properties": table_data,
        "device_info": device_info,
        "alert_history": alert_history,
        "meta": {
            "lag_seconds": round(lag, 1),
            "motion_artifact": motion_artifact,
            "sleeping": sleeping,
            "sleep_session": {
                "active": session_active,
                "total_session_seconds": round(total_session),
                "total_sleep_seconds": round(total_sleep),
                "light_seconds": round(_sleep_session["light_secs"]),
                "deep_seconds": round(_sleep_session["deep_secs"]),
                "awake_seconds": round(_sleep_session["awake_secs"]),
            },
        },
    }
