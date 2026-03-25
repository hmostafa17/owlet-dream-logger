# Owlet Dream Logger

Real-time monitoring dashboard for the **Owlet Smart Sock 3**. Displays live baby vitals (heart rate, oxygen saturation, movement), logs all data to CSV, and provides detailed device diagnostics.

Available as both a **web dashboard** (FastAPI) and a **standalone desktop app** (CustomTkinter).

![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

## Features

- **Live Vitals** — Heart rate, SpO2, skin temperature, and movement streamed every 2 seconds
- **Device State Machine** — Computed device state: Monitoring, Charging, Charged, No Signal, Disconnected — using LIR (Low Integrity Read) truth table logic
- **Alarm Priority System** — 3-tier alarm level (HIGH / MED / LOW) from `PREVIEW_*_PRIORITY_ALARM` properties
- **Device Alerts** — Real-time Owlet alerts: low oxygen, high/low HR, critical battery, sock off, sock disconnected, low signal (yellow light)
- **Color-Coded Ranges** — HR and oxygen values change color based on clinical ranges
- **Quality Badges** — LIVE, CALIBRATING, WEAK, IDLE, DOCKED status indicators based on band placement state
- **Stale Data Detection** — Warnings when the base station loses connection, with automatic multi-stage recovery
- **Motion Artifact Detection** — Flags unreliable readings during high baby movement (mvb ≥ 50%)
- **Wake Detection** — Alerts when sleep state transitions from sleep to awake
- **Sleep Session Tracking** — Tracks total session time with per-state breakdown (Deep, Light, Awake). Brief awakenings don't reset the session — only docking the sock ends it. On startup, queries Ayla datapoint history to recover in-progress sessions.
- **Technical Diagnostics** — Battery, WiFi signal, sock placement, sleep state, skin temp, charging status
- **CSV Logging** — Every reading automatically saved to `owlet_data_log.csv`
- **Token Auto-Refresh** — Long-running sessions stay connected without re-authentication
- **Device Insights** — Firmware versions, MAC addresses, monitoring settings, and decoded alert history (desktop: Device Insights tab)
- **Alert History Summary** — Decoded RED_ALERT_SUMMARY showing HR, SpO2, duration, and type for every alert event
- **Two Interfaces** — Web dashboard for multi-device access, desktop app for simplicity

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run

**Web dashboard** (accessible from any device on your network):

```bash
python main.py
# Open http://localhost:8000
```

**Desktop app** (standalone window, no browser needed):

```bash
python desktop_app.py
```

## Project Structure

```
owlet/
├── main.py                 # FastAPI web server entry point
├── desktop_app.py          # Standalone desktop GUI (CustomTkinter)
├── launcher.py             # Launcher for .exe builds (PyInstaller)
├── config.py               # Application settings
├── worker.py               # Background Owlet API polling loop
├── owlet_service.py        # Device discovery
├── data_processing.py      # Raw data → structured vitals
├── csv_logger.py           # CSV file logging
├── session.py              # In-memory session store (web mode)
├── dashboard.py            # Web dashboard HTML/CSS/JS
├── login_page.py           # Web login page HTML/CSS/JS
├── debug_api.py            # API debug tool (downloads logs, decodes alerts)
├── Start_Owlet_Logger.bat  # Windows batch launcher
├── requirements.txt        # Python dependencies
└── BUILDING.md             # Instructions for creating .exe
```

## Configuration

Edit `config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `UPDATE_INTERVAL` | `2` | Seconds between data fetches |
| `LOG_FILE` | `owlet_data_log.csv` | CSV output path |
| `HOST` | `0.0.0.0` | Server bind address (web mode) |
| `PORT` | `8000` | Server port (web mode) |

## Vitals Color Ranges

**Heart Rate (BPM):**
| Range | Color | Meaning |
|-------|-------|---------|
| 100–160 | Green | Normal |
| 90–99 / 161–180 | Yellow | Alert |
| <90 / >180 | Red | Critical |

**Oxygen Saturation (SpO2):**
| Range | Color | Meaning |
|-------|-------|---------|
| ≥95% | Blue | Normal |
| 90–94% | Yellow | Low |
| <90% | Red | Very Low |

## CSV Data Columns

Each row in `owlet_data_log.csv` contains:

`timestamp_log`, `lag_seconds`, `hr`, `ox`, `oxta`, `mv`, `mvb`, `rsi`, `ss`, `sc`, `bat`, `btt`, `chg`, `onm`, `bso`, `bp`, `mrs`, `hw`, `st`, `srf`

## REAL_TIME_VITALS Field Reference

All live vitals for the Smart Sock 3 are delivered as a single JSON string in the `REAL_TIME_VITALS` Ayla Networks property. The following field descriptions were reverse-engineered from the [pyowletapi](https://github.com/ryanbdclark/pyowletapi) source code, multiple open-source projects, and cross-referenced against 1,956 real device data points.

### Vitals (Medical Readings)

| Key | Name | Type | Description |
|-----|------|------|-------------|
| `hr` | Heart Rate | float | BPM. 0 when sock is not reading (docked/off-foot). Normal infant range: 100–160. |
| `ox` | Oxygen Saturation | float | SpO2 percentage. 0 = no reading. Normal: ≥95%. |
| `oxta` | Oxygen 10s Average | float | Rolling 10-second SpO2 average. **255 = sentinel "no data"** (sock not reading). |
| `st` | Skin Temperature | int | Skin temperature sensor value. May read 0 on some firmware versions. |

### Movement

| Key | Name | Type | Description |
|-----|------|------|-------------|
| `mv` | Movement (raw) | int | Raw accelerometer intensity (observed 0–146). Higher = more movement. |
| `mvb` | Movement Bucket | int | Normalized movement on a 0–100% scale. Non-linear bucketing of `mv` into percentiles. |

### Sleep State

| Key | Name | Type | Values |
|-----|------|------|--------|
| `ss` | Sleep State | int | **0** = Inactive (not monitoring, hr=0). **1** = Awake (high movement, variable HR). **8** = Light Sleep (very low movement, steady HR). **15** = Deep Sleep (near-zero movement, lowest HR). |

Observed correlations from real device data:

| State | Avg HR | Avg Movement | Interpretation |
|-------|--------|--------------|----------------|
| ss=0 | 0 | 0.0 | Sock not on baby or base station off |
| ss=1 | 108 | 19.1 | Baby awake and moving |
| ss=8 | 114 | 0.6 | Light / REM sleep |
| ss=15 | 106 | 0.1 | Deep sleep |

### Power & Battery

| Key | Name | Type | Description |
|-----|------|------|-------------|
| `bat` | Battery Percentage | float | Sock battery level 0–100%. |
| `btt` | Battery Time | float | Estimated remaining battery in **minutes** (e.g. 1145 ≈ 19 hours). 0 when on base. |
| `chg` | Charging Status | int | **0** = Not charging. **1** = Charging. **2** = Fully charged. |
| `bso` | Base Station On | int | **0** = Base station off / sock docked idle. **1** = Base station actively powered. |
| `bsb` | Base Battery Status | int | Base station battery backup status. **2** = battery backup present and charged. |

### Connectivity

| Key | Name | Type | Description |
|-----|------|------|-------------|
| `rsi` | Signal Strength | float | WiFi/BLE RSSI signal quality indicator (higher = better, observed 37–46). |
| `sc` | Sock Connection | int | Sock-to-base connection status. **2** = connected and active. |

### Band Placement (`bp`) — State Machine

The `bp` field represents the sock sensor signal quality state. This field is **not mapped by pyowletapi** and was reverse-engineered from real device data patterns:

| bp | State | Evidence |
|----|-------|----------|
| **7** | Idle / Docked | hr=0, ox=0, bso=0, chg=2. Sock sitting on fully charged base, not monitoring. |
| **1** | Calibrating | hr=97–188 (avg 158), ox=100. Very high/erratic HR — sensor still locking on after placement. |
| **8** | Stabilizing | hr=100–115, ox=99–100, ss=8. Intermediate re-lock state ~45 sec. Sensor adjusting after signal disruption. Always transitions 8→1→10. |
| **9** | Acquiring | hr=109–119, ox=98–99, ss=15. Sock placed on baby, reading vitals but signal not fully optimized. Transitions from bp=7 (docked). |
| **10** | Active Monitoring | hr=84–134, ox=99–100, bso=1. Best quality readings — sock properly placed and reading. |
| **11** | Settling | hr=109–129, ox=97–100. Brief 2–5 sec transition when monitoring quality drops. Precedes 9 (re-acquire) or 8 (stabilize). |
| **6** | Signal Degraded | hr=0–130, ox=0–100. Mixed readings — sometimes valid, sometimes lost. 141 of 448 rows had ox=0. |

Observed state transitions: `7 → 9 → 10` (docked → acquiring → monitoring), `7 → 1 → 10` (docked → calibrating → monitoring), `10 → 11 → 9 → 1 → 10` (settling → re-acquiring → recalibrating), `10 → 11 → 8 → 1 → 10` (settling → stabilizing → recalibrating), `10 ↔ 1` (brief recalibrations), `10 → 6 → 7` (signal loss → idle).

### Motion Artifact Detection

When the baby is moving heavily (`mvb ≥ 50%`), pulse oximetry readings become unreliable due to motion artifact. The app detects this and:

- **Softens color coding** — HR/SpO2 values that would normally show red are downgraded to yellow
- **Shows "MOVING" badge** — replaces the normal quality badge on the HR card
- **Displays warning text** — "⚡ Motion artifact — reading may be inaccurate" on both HR and SpO2 cards
- **Context-aware bp=1** — when bp=1 during high movement, shows "Moving (1)" instead of "Calibrating (1)"

Real-world example: HR at 190 BPM with mvb=83% and SpO2 dipping to 92% — both are motion artifacts, not true cardiac events.

### Wake Detection

The app monitors sleep state (`ss`) transitions and alerts when the baby wakes up:
- Triggers when `ss` changes from **8** (Light Sleep) or **15** (Deep Sleep) to **1** (Awake)
- Displays a "👶 Baby woke up!" alert banner
- Correlates with movement spikes (`mvb` and `mv` increases)

### Sleep Session Tracking

The app tracks sleep sessions with per-state time breakdowns, designed to handle real infant sleep patterns:

| Field | Description |
|-------|-------------|
| **Total session** | Wall-clock time from first sleep to dock (includes brief awakenings) |
| **Total sleep** | Accumulated time in Light + Deep sleep only |
| 🌙 **Deep** | Time in `ss=15` (Deep Sleep) |
| 💤 **Light** | Time in `ss=8` (Light Sleep) |
| 👀 **Awake** | Time in `ss=1` (Awake) *during* the session |

**Session lifecycle:**
- **Starts** when `ss` first enters 8 (Light) or 15 (Deep)
- **Continues** through brief awakenings (`ss=1`) — babies naturally cycle between sleep states with short wake periods
- **Ends only** when the sock is docked (`chg=1` or `chg=2`)
- **Startup recovery** — if the app starts while a session is in progress, it queries the Ayla `/datapoints.json` API to walk back through REAL_TIME_VITALS history and find the true session start (stopping at any docking event)

All timestamps use the server-side `data_updated_at` field from the Ayla cloud, not the local clock, so the timer is accurate even if the app was restarted mid-session.

### Monitoring State

| Key | Name | Type | Description |
|-----|------|------|-------------|
| `onm` | Wellness Alert Mode | int | Monitoring mode setting. **3** = Active monitoring. Echoed from `SETTINGS_STATUS`. |
| `mrs` | Monitor Ready Status | int | Monitoring subsystem initialization flag. **1** = ready. |
| `mst` | Monitor Start Time | int | Timestamp-like value for when monitoring session started. 0 when idle. |
| `srf` | Sensor Readings Flag | int | Whether sensor has valid reading capability. **1** = readings available. |

### Alerts & OTA

| Key | Name | Type | Description |
|-----|------|------|-------------|
| `alrt` | Alerts Mask | int | Bitmask of currently active alert types. **0** = no active alerts. |
| `aps` | Alert Paused Status | int | Whether alert notifications are paused. **0** = alerts active, **1** = paused. |
| `ota` | OTA Update Status | int | Over-the-air firmware update status. **0** = no update in progress. |
| `sb` | Brick Status | int | Hardware fault / bricked state. **0** = normal operation. |

### Hardware

| Key | Name | Type | Description |
|-----|------|------|-------------|
| `hw` | Hardware Version | str | Hardware revision identifier (e.g. `"obs4"` = Owlet Base Station revision 4). |

### Separate Ayla Properties (outside REAL_TIME_VITALS)

These properties are individual Ayla datapoints (not inside the REAL_TIME_VITALS JSON):

| Property | Description |
|----------|-------------|
| `LOW_INTEG_READ` | **Low Integrity Read** — the Owlet "yellow light." Sock is connected but sensor cannot get a valid reading. |
| `PREVIEW_HIGH_PRIORITY_ALARM` | **High priority alarm** active (critical oxygen, critical HR). |
| `PREVIEW_MED_PRIORITY_ALARM` | **Medium priority alarm** active (out-of-range vitals). |
| `PREVIEW_LOW_PRIORITY_ALARM` | **Low priority alarm** active (low battery, placement issue). |
| `LOW_OX_ALRT`, `CRIT_OX_ALRT` | Low / critical oxygen saturation alert. |
| `LOW_HR_ALRT`, `HIGH_HR_ALRT` | Low / high heart rate alert. |
| `LOW_BATT_ALRT`, `CRIT_BATT_ALRT` | Low / critical battery alert. |
| `SOCK_OFF`, `SOCK_DISCON_ALRT` | Sock removed or disconnected from base. |
| `LOST_POWER_ALRT` | Base station lost power. |
| `DISCOMFORT_ALRT` | Baby discomfort detected. |
| `RED_ALERT_SUMMARY` | Base64-encoded alert history (decoded in Device Insights). |

### Device State Machine (LIR Logic)

The app computes a high-level device state using the **LIR (Low Integrity Read) truth table** from [jlamendo/ha-sensor.owlet](https://github.com/jlamendo/ha-sensor.owlet):

```
LIR = LOW_INTEG_READ OR (HR=0 AND SpO2=0 AND no HR/OX alerts)
```

| State | Condition | Meaning |
|-------|-----------|---------|
| **Monitoring** | LIR=false | Good readings — sock properly placed, vitals streaming |
| **No Signal** | LIR=true, not charging | Yellow light — sock on but no sensor contact |
| **Charging** | LIR=true, chg=1 | Sock charging on base station |
| **Charged** | LIR=true, chg=2 | Sock fully charged, sitting on base |
| **Disconnected** | bso≠1 AND LIR=true | Base station off and no readings |

### Alarm Priority System

Three-tier alarm system from `PREVIEW_*_PRIORITY_ALARM` properties:

| Priority | Badge | Typical Triggers |
|----------|-------|-----------------|
| **HIGH** | 🔴 ⚠ HIGH | Critical oxygen, critical heart rate |
| **MED** | 🟡 ⚠ MED | Out-of-range vitals, discomfort |
| **LOW** | 🔵 ⚠ LOW | Low battery, placement issues |

## Stall Recovery System

The Owlet base station requires a periodic `APP_ACTIVE=1` heartbeat via the Ayla cloud API to keep pushing `REAL_TIME_VITALS`. If this heartbeat is missed (due to token expiry, an API hiccup, or a pyowletapi bug where `activate()` calls `self.authenticate()` without `await`), the base station stops updating vitals while continuing to process alerts locally (which is why you still get phone notifications during a stall).

The worker implements a multi-stage automatic recovery:

| Stage | Trigger | Action | Effect |
|-------|---------|--------|--------|
| **Proactive** | Every 25s | Explicit `APP_ACTIVE=1` POST with fresh token | Prevents most stalls from occurring |
| **0 — Normal** | lag < 30s | Standard polling | Green status |
| **1 — Re-auth** | 5 consecutive stale cycles | Force token refresh + explicit `APP_ACTIVE` | Fixes token expiry stalls (~80% of cases) |
| **2 — Rebuild** | 15 consecutive stale cycles | Tear down and recreate entire API session | Fixes stuck sessions, routing issues |
| **Backoff** | During stage 2 | Polling slowed to 5s | Avoids rate-limiting during recovery |

Additionally, all `update_properties()` calls have a 15-second timeout to prevent the worker from hanging on a stuck API connection.

## Building a Standalone .exe

See [BUILDING.md](BUILDING.md) for instructions on creating a portable Windows executable using PyInstaller.

## Dependencies

- [pyowletapi](https://github.com/ryanbdclark/pyowletapi) — Owlet cloud API client
- [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) — Web server (web mode)
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — Modern desktop GUI (desktop mode)

## License

MIT — see [LICENSE](LICENSE) for details.
