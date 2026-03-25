"""
Debug script to inspect raw Owlet API data and download device logs.

Usage:
    python debug_api.py <email> <password> [region]
    region: europe or world (default: europe)
"""

import asyncio
import base64
from datetime import datetime, timezone
import json
import os
import struct
import sys

import aiohttp

from pyowletapi.api import OwletAPI
from pyowletapi.sock import Sock


# ---------------------------------------------------------------------------
# Binary log parsers
# ---------------------------------------------------------------------------

def format_seq(seq):
    """Format a sequence number — decode as timestamp if it looks like a Unix epoch."""
    # Unix timestamps from 2024-2030 range: ~1704067200 to ~1893456000
    if 1_700_000_000 <= seq <= 1_900_000_000:
        dt = datetime.fromtimestamp(seq, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    return str(seq)


def parse_msc_error_log(data):
    """Parse MSC-format error logs into readable messages.
    Format: MSC\\xfe header, then records of \\x07 + len(1) + seq(4) + ascii message.
    """
    messages = []
    if len(data) < 6 or data[:3] != b"MSC":
        return messages

    # Skip past the MSC header — scan for first \x07 record marker
    i = 4
    # Skip version/flags bytes until first \x07
    while i < len(data) and data[i] != 0x07:
        i += 1

    while i < len(data):
        if data[i] != 0x07:
            i += 1
            continue
        i += 1  # skip marker
        if i >= len(data):
            break
        msg_len = data[i]
        i += 1  # skip length
        if i + 4 > len(data):
            break
        seq = struct.unpack_from("<I", data, i)[0]
        i += 4  # skip sequence
        if i + msg_len > len(data):
            msg_len = len(data) - i
        msg = data[i:i + msg_len].decode("utf-8", errors="replace")
        i += msg_len
        messages.append({"seq": seq, "timestamp": format_seq(seq), "message": msg})
    return messages


def parse_red_alert_summary(data):
    """Parse RED_ALERT_SUMMARY as 8-byte header + 5-byte alert records.
    Each record: HR(1), SpO2(1), duration(1), type(1), flags(1).
    """
    if len(data) < 10:
        return None, []

    # 10-byte header
    header = data[:10]
    records = []
    i = 10
    while i + 5 <= len(data):
        hr = data[i]
        ox = data[i + 1]
        duration = data[i + 2]
        alert_type = data[i + 3]
        flags = data[i + 4]
        # Skip null records (all zeros = padding)
        if hr == 0 and ox == 0 and duration == 0 and alert_type == 0 and flags == 0:
            i += 5
            continue
        # Filter plausible vitals (HR 40-250, SpO2 50-100)
        # or allow type=2 separator records
        records.append({
            "hr": hr, "ox": ox, "duration": duration,
            "type": alert_type, "flags": flags
        })
        i += 5

    return header, records


ALERT_TYPE_NAMES = {
    1: "LOW_OX",
    2: "CRIT_OX",
    3: "LOW_HR",
    4: "HIGH_HR",
    5: "CRIT_BATT",
    6: "GENERAL",
    7: "SOCK_OFF",
    8: "SOCK_DISCON",
}


def parse_vitals_log(data):
    """Parse VITALS_LOG_FILE binary data.
    Record pattern: [status_hi status_lo] 08 seq(1) [extra(1)] HR(1) [extra(1)]
    The \x08 marker precedes each reading with an incrementing sequence byte.
    """
    readings = []
    if len(data) < 48:
        return readings

    # Scan for \x08 markers followed by sequence + HR data
    i = 0
    while i < len(data) - 4:
        if data[i] == 0x08:
            seq = data[i + 1]
            # Pattern A: 08 seq flags HR extra  (common)
            # Pattern B: 08 seq HR extra        (when flags=0 is omitted)
            # Heuristic: check which of data[i+2] or data[i+3] is a plausible HR
            b2 = data[i + 2]
            b3 = data[i + 3]
            b4 = data[i + 4] if i + 4 < len(data) else 0

            hr = None
            ox = None
            flags = 0

            if 60 <= b3 <= 220:  # b2=flags, b3=HR
                flags = b2
                hr = b3
                ox = b4 if 50 <= b4 <= 100 else None
            elif 60 <= b2 <= 220:  # b2=HR directly (no flags byte)
                hr = b2
                ox = b3 if 50 <= b3 <= 100 else None

            if hr is not None:
                readings.append({"seq": seq, "hr": hr, "ox": ox, "flags": flags})
            i += 4
        else:
            i += 1

    return readings


async def main():
    if len(sys.argv) < 3:
        print(f"Usage: python {sys.argv[0]} <email> <password> [region]")
        print(f"  region: europe or world (default: europe)")
        sys.exit(1)

    email = sys.argv[1]
    password = sys.argv[2]
    region = sys.argv[3] if len(sys.argv) > 3 else "europe"

    api = OwletAPI(region, email, password)
    try:
        print("\n[1] Authenticating...")
        await api.authenticate()
        print("    OK")

        print("\n[2] Getting devices...")
        devices_resp = await api.get_devices()

        # Normalize response
        if isinstance(devices_resp, dict) and "response" in devices_resp:
            devices_list = devices_resp["response"]
        elif isinstance(devices_resp, list):
            devices_list = devices_resp
        else:
            print(f"    Unexpected response type: {type(devices_resp)}")
            print(f"    Raw: {devices_resp}")
            return

        print(f"    Found {len(devices_list)} device(s)")

        for i, entry in enumerate(devices_list):
            dev = entry.get("device", {})
            print(f"\n{'='*60}")
            print(f"DEVICE {i+1}")
            print(f"{'='*60}")
            print(f"  product_name : {dev.get('product_name')}")
            print(f"  model        : {dev.get('model')}")
            print(f"  dsn          : {dev.get('dsn')}")
            print(f"  oem_model    : {dev.get('oem_model')}")
            print(f"  sw_version   : {dev.get('sw_version')}")
            print(f"  conn_status  : {dev.get('connection_status')}")

            print(f"\n[3] Creating Sock object and fetching properties...")
            sock = Sock(api, dev)
            result = await sock.update_properties()

            # Show normalized properties from pyowletapi
            print(f"\n--- sock.properties (normalized by pyowletapi) ---")
            if sock.properties:
                for k, v in sorted(sock.properties.items()):
                    print(f"  {k:30s} = {v}")
            else:
                print("  (empty)")

            print(f"\n--- sock metadata ---")
            print(f"  version  : {sock.version}")
            print(f"  revision : {getattr(sock, 'revision', 'N/A')}")

            # Check for BABY_NAME specifically
            print(f"\n--- BABY_NAME check ---")
            raw = sock.raw_properties
            if "BABY_NAME" in raw:
                bn = raw["BABY_NAME"]
                print(f"  FOUND! value = {bn.get('value')!r}")
                print(f"  full entry: {json.dumps(bn, indent=2, default=str)}")
            else:
                print("  NOT in raw_properties")
                # Search for anything with 'baby' or 'name' in the key
                matches = [k for k in raw.keys() if "baby" in k.lower() or "name" in k.lower()]
                if matches:
                    print(f"  But found related keys: {matches}")
                    for m in matches:
                        print(f"    {m} = {raw[m].get('value')!r}")
                else:
                    print("  No keys containing 'baby' or 'name' found")

            # Show ALL property keys
            print(f"\n--- All {len(raw)} raw property keys ---")
            for k in sorted(raw.keys()):
                val = raw[k].get("value") if isinstance(raw[k], dict) else raw[k]
                # Truncate long values
                val_str = str(val)
                if len(val_str) > 80:
                    val_str = val_str[:80] + "..."
                print(f"  {k:35s} = {val_str}")

            # Show REAL_TIME_VITALS decoded
            if "REAL_TIME_VITALS" in raw:
                rtv = raw["REAL_TIME_VITALS"]
                print(f"\n--- REAL_TIME_VITALS decoded ---")
                print(f"  data_updated_at: {rtv.get('data_updated_at')}")
                try:
                    vitals = json.loads(rtv.get("value", "{}"))
                    for k, v in sorted(vitals.items()):
                        print(f"  {k:10s} = {v}")
                except:
                    print(f"  raw value: {rtv.get('value')}")

            # Show alert-related properties
            print(f"\n--- Alert properties ---")
            alert_keys = [k for k in raw.keys() if "ALRT" in k or "SOCK_OFF" in k or "LOST_POWER" in k]
            for k in sorted(alert_keys):
                val = raw[k].get("value") if isinstance(raw[k], dict) else raw[k]
                print(f"  {k:25s} = {val}")

            # --- SETTINGS & CONFIG ---
            print(f"\n--- Device Settings ---")
            if "SETTINGS_STATUS" in raw and isinstance(raw["SETTINGS_STATUS"], dict):
                try:
                    settings = json.loads(raw["SETTINGS_STATUS"]["value"])
                    s = settings.get("settings", {})
                    print(f"  Monitoring mode (onm)  : {s.get('onm')}")
                    print(f"  Oxygen baseline (blox) : {s.get('blox')}")
                    print(f"  HR baseline (blhr)     : {s.get('blhr')}")
                    print(f"  Sleep state (sst)      : {s.get('sst')}")
                    print(f"  Sleep mode (slm)       : {s.get('slm')}")
                    print(f"  Full: {json.dumps(settings, indent=2)}")
                except Exception as e:
                    print(f"  Parse error: {e}")

            if "CONFIG_STATUS" in raw and isinstance(raw["CONFIG_STATUS"], dict):
                try:
                    config = json.loads(raw["CONFIG_STATUS"]["value"])
                    print(f"\n--- Config ---")
                    print(f"  Sock MAC  : {config.get('smac')}")
                    print(f"  Base MAC  : {config.get('bmac')}")
                except:
                    pass

            # --- FIRMWARE INFO ---
            print(f"\n--- Firmware ---")
            if "oem_base_version" in raw and isinstance(raw["oem_base_version"], dict):
                try:
                    fw = json.loads(raw["oem_base_version"]["value"])
                    print(f"  Base app     : {fw.get('app')}")
                    print(f"  Base hardware: {fw.get('hw')}")
                    print(f"  Base revision: {fw.get('rev')}")
                except:
                    print(f"  Raw: {raw['oem_base_version'].get('value')}")

            if "oem_sock_version" in raw and isinstance(raw["oem_sock_version"], dict):
                try:
                    fw = json.loads(raw["oem_sock_version"]["value"])
                    print(f"  Sock app     : {fw.get('app')}")
                    print(f"  Sock SD      : {fw.get('sd')}")
                    print(f"  Sock bootldr : {fw.get('bl')}")
                except:
                    print(f"  Raw: {raw['oem_sock_version'].get('value')}")

            if "oem_flash_version" in raw and isinstance(raw["oem_flash_version"], dict):
                print(f"  Flash version: {raw['oem_flash_version'].get('value')}")

            # --- DOWNLOAD LOG FILES ---
            print(f"\n{'='*60}")
            print(f"DOWNLOADING LOG FILES")
            print(f"{'='*60}")

            log_dir = "debug_logs"
            os.makedirs(log_dir, exist_ok=True)

            log_properties = [
                "PPG_LOG_FILE",
                "VITALS_LOG_FILE",
                "BASE_ERROR_LOG_FILE",
                "SENSOR_ERROR_LOG_FILE",
                "BASE_EVT_LOG_FILE",
                "MISC_LOG_FILE_DATA",
                "VITALS_LOG_DATA",
            ]

            auth_headers = dict(api.headers)

            for prop_name in log_properties:
                if prop_name not in raw or not isinstance(raw[prop_name], dict):
                    print(f"\n  [{prop_name}] Not in properties")
                    continue

                url = raw[prop_name].get("value")
                if not url or url == "None" or not isinstance(url, str) or not url.startswith("http"):
                    print(f"\n  [{prop_name}] No URL (value: {url})")
                    continue

                print(f"\n  [{prop_name}]")
                print(f"    Metadata URL: {url}")

                try:
                    async with aiohttp.ClientSession() as dl_session:
                        # Step 1: Fetch datapoint metadata JSON
                        async with dl_session.get(url, headers=auth_headers) as resp:
                            if resp.status != 200:
                                print(f"    Metadata fetch failed: {resp.status}")
                                continue
                            meta_data = await resp.json()

                        dp = meta_data.get("datapoint", {})
                        file_url = dp.get("file")
                        print(f"    Created: {dp.get('created_at')}")
                        print(f"    Updated: {dp.get('updated_at')}")

                        # Save metadata JSON
                        meta_file = os.path.join(log_dir, f"{prop_name}_meta.json")
                        with open(meta_file, "w") as f:
                            json.dump(meta_data, f, indent=2)

                        if not file_url:
                            print(f"    No file URL in datapoint")
                            continue

                        print(f"    File URL: {file_url[:100]}...")

                        # Step 2: Download the actual binary log file
                        async with dl_session.get(file_url) as resp2:
                            print(f"    Download status: {resp2.status}")
                            if resp2.status == 200:
                                binary_data = await resp2.read()
                                ct = resp2.headers.get("Content-Type", "unknown")
                                print(f"    Content-Type: {ct}")
                                print(f"    File size: {len(binary_data)} bytes")

                                if "json" in ct:
                                    ext = ".json"
                                elif "text" in ct:
                                    ext = ".txt"
                                else:
                                    ext = ".bin"

                                data_file = os.path.join(log_dir, f"{prop_name}{ext}")
                                with open(data_file, "wb") as f:
                                    f.write(binary_data)
                                print(f"    Saved: {data_file}")

                                # Preview the data
                                if ext in (".json", ".txt"):
                                    text = binary_data.decode("utf-8", errors="replace")
                                    if len(text) > 600:
                                        text = text[:600] + "\n    ... (truncated)"
                                    print(f"    Preview:\n    {text}")
                                else:
                                    # Hex dump for binary
                                    print(f"    Hex dump (first 128 bytes):")
                                    for offset in range(0, min(128, len(binary_data)), 16):
                                        chunk = binary_data[offset:offset+16]
                                        hex_part = " ".join(f"{b:02x}" for b in chunk)
                                        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                                        print(f"      {offset:04x}: {hex_part:<48s}  {ascii_part}")
                                    if len(binary_data) > 128:
                                        print(f"      ... ({len(binary_data) - 128} more bytes)")

                                # --- Parse known formats ---
                                if "ERROR_LOG" in prop_name and binary_data[:3] == b"MSC":
                                    msgs = parse_msc_error_log(binary_data)
                                    if msgs:
                                        print(f"\n    === PARSED ERROR LOG ({len(msgs)} entries) ===")
                                        for m in msgs:
                                            ts = m['timestamp']
                                            print(f"      [{ts}] {m['message']}")

                                        # Save as readable text (UTF-8)
                                        txt_file = os.path.join(log_dir, f"{prop_name}_parsed.txt")
                                        with open(txt_file, "w", encoding="utf-8") as f:
                                            for m in msgs:
                                                f.write(f"[{m['timestamp']}] {m['message']}\n")
                                        print(f"    Saved readable: {txt_file}")

                                elif prop_name == "PPG_LOG_FILE" and binary_data[:3] == b"MSC":
                                    # PPG data — extract float values for analysis
                                    n_floats = (len(binary_data) - 9) // 4
                                    print(f"\n    === PPG WAVEFORM ANALYSIS ===")
                                    print(f"    MSC version: {binary_data[4]}.{binary_data[5]}")
                                    print(f"    Estimated float samples: ~{n_floats}")
                                    # Try to extract IEEE 754 floats
                                    floats = []
                                    for off in range(9, len(binary_data) - 3, 4):
                                        try:
                                            val = struct.unpack_from("<f", binary_data, off)[0]
                                            if 0.0 < abs(val) < 100.0:
                                                floats.append(val)
                                        except:
                                            pass
                                    if floats:
                                        print(f"    Valid float values found: {len(floats)}")
                                        print(f"    Range: {min(floats):.4f} to {max(floats):.4f}")
                                        print(f"    Mean: {sum(floats)/len(floats):.4f}")

                                elif prop_name == "VITALS_LOG_FILE":
                                    readings = parse_vitals_log(binary_data)
                                    if readings:
                                        print(f"\n    === VITALS LOG ANALYSIS ===")
                                        print(f"    Extracted {len(readings)} readings")
                                        hrs = [r["hr"] for r in readings]
                                        oxs = [r["ox"] for r in readings if r["ox"] is not None]
                                        print(f"    HR range: {min(hrs)} - {max(hrs)} BPM")
                                        print(f"    HR mean:  {sum(hrs)/len(hrs):.0f} BPM")
                                        if oxs:
                                            print(f"    SpO2 range: {min(oxs)} - {max(oxs)}%")
                                            print(f"    SpO2 mean:  {sum(oxs)/len(oxs):.0f}%")
                                        print(f"    First 30 readings:")
                                        for r in readings[:30]:
                                            ox_str = f"{r['ox']:3d}%" if r['ox'] else "  - "
                                            print(f"      seq={r['seq']:3d}  HR={r['hr']:3d}  SpO2={ox_str}  flags=0x{r['flags']:02x}")

                                        # Save as CSV
                                        csv_file = os.path.join(log_dir, f"VITALS_LOG_extracted.csv")
                                        with open(csv_file, "w", encoding="utf-8") as f:
                                            f.write("seq,hr,spo2,flags\n")
                                            for r in readings:
                                                ox_val = r['ox'] if r['ox'] is not None else ''
                                                f.write(f"{r['seq']},{r['hr']},{ox_val},{r['flags']}\n")
                                        print(f"    Saved CSV: {csv_file}")
                            else:
                                body = await resp2.text()
                                print(f"    Download failed: {resp2.status}")
                                print(f"    Body: {body[:300]}")
                except Exception as e:
                    print(f"    Error: {e}")

            # --- ENCODED DATA FIELDS ---
            print(f"\n{'='*60}")
            print(f"ENCODED DATA FIELDS (BASE64 DECODED)")
            print(f"{'='*60}")

            for field in ["MONITORING_SUMMARY", "RED_ALERT_SUMMARY", "MOBILE_VITALS"]:
                if field not in raw or not isinstance(raw[field], dict):
                    continue
                val = raw[field].get("value")
                if not val or val == "None":
                    continue

                val_str = str(val)
                print(f"\n  [{field}]")
                print(f"    Raw length: {len(val_str)} chars")
                print(f"    Raw: {val_str[:120]}{'...' if len(val_str) > 120 else ''}")

                # Save raw value
                filename = os.path.join(log_dir, f"{field}_raw.txt")
                with open(filename, "w") as f:
                    f.write(val_str)

                # Try base64 decode
                try:
                    # Pad if needed
                    padded = val_str + "=" * (-len(val_str) % 4)
                    decoded = base64.b64decode(padded)
                    print(f"    Decoded size: {len(decoded)} bytes")

                    # Save decoded binary
                    bin_file = os.path.join(log_dir, f"{field}_decoded.bin")
                    with open(bin_file, "wb") as f:
                        f.write(decoded)
                    print(f"    Saved decoded: {bin_file}")

                    if field == "MONITORING_SUMMARY":
                        print(f"    Byte analysis ({len(decoded)} bytes):")
                        for i, b in enumerate(decoded):
                            print(f"      byte[{i:2d}] = {b:3d} (0x{b:02x})")

                    elif field == "RED_ALERT_SUMMARY":
                        header, records = parse_red_alert_summary(decoded)
                        if header is not None:
                            print(f"    Header (10 bytes): {' '.join(f'{b:02x}' for b in header)}")
                        print(f"\n    === ALERT HISTORY ({len(records)} events) ===")
                        print(f"    {'#':>4s}  {'HR':>4s}  {'SpO2':>4s}  {'Dur':>4s}  {'Type':>4s}  Alert")
                        print(f"    {'─'*4}  {'─'*4}  {'─'*4}  {'─'*4}  {'─'*4}  {'─'*15}")
                        for i, r in enumerate(records):
                            type_name = ALERT_TYPE_NAMES.get(r["type"], f"TYPE_{r['type']}")
                            print(f"    {i+1:4d}  {r['hr']:4d}  {r['ox']:4d}  {r['duration']:4d}  {r['type']:4d}  {type_name}")

                        if records:
                            hrs = [r["hr"] for r in records if 40 <= r["hr"] <= 250]
                            oxs = [r["ox"] for r in records if 50 <= r["ox"] <= 100]
                            print(f"\n    Summary:")
                            print(f"      Total alert events: {len(records)}")
                            if hrs:
                                print(f"      HR during alerts: {min(hrs)}-{max(hrs)} BPM (avg {sum(hrs)//len(hrs)})")
                            if oxs:
                                print(f"      SpO2 during alerts: {min(oxs)}-{max(oxs)}%")
                            # Count by type
                            type_counts = {}
                            for r in records:
                                t = ALERT_TYPE_NAMES.get(r["type"], f"TYPE_{r['type']}")
                                type_counts[t] = type_counts.get(t, 0) + 1
                            print(f"      By type: {type_counts}")

                        # Save as CSV
                        csv_file = os.path.join(log_dir, f"RED_ALERT_SUMMARY.csv")
                        with open(csv_file, "w", encoding="utf-8") as f:
                            f.write("event,hr,spo2,duration,type,type_name\n")
                            for i, r in enumerate(records):
                                type_name = ALERT_TYPE_NAMES.get(r["type"], f"TYPE_{r['type']}")
                                f.write(f"{i+1},{r['hr']},{r['ox']},{r['duration']},{r['type']},{type_name}\n")
                        print(f"    Saved CSV: {csv_file}")

                    elif field == "MOBILE_VITALS":
                        pass  # JSON, no further decoding needed
                except Exception as e:
                    print(f"    Base64 decode failed: {e}")
                    # Maybe it's just JSON
                    try:
                        parsed = json.loads(val_str)
                        print(f"    JSON: {json.dumps(parsed, indent=2)}")
                    except:
                        pass

            print(f"\n{'='*60}")
            print(f"All files saved to: {os.path.abspath(log_dir)}/")
            print(f"{'='*60}")
            print()

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await api.close()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
