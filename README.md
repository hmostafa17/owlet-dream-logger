# Owlet Dream Logger

Real-time monitoring dashboard for the **Owlet Smart Sock 3**. Displays live baby vitals (heart rate, oxygen saturation, movement), logs all data to CSV, and provides detailed device diagnostics.

Available as both a **web dashboard** (FastAPI) and a **standalone desktop app** (CustomTkinter).

![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

## Features

- **Live Vitals** — Heart rate, SpO2, skin temperature, and movement streamed every 2 seconds
- **Device Alerts** — Real-time Owlet alerts: low oxygen, high/low HR, critical battery, sock off, sock disconnected
- **Color-Coded Ranges** — HR and oxygen values change color based on clinical ranges
- **Quality Badges** — LIVE, CALIBRATING, WEAK, IDLE, DOCKED status indicators based on band placement state
- **Stale Data Detection** — Warnings when the base station loses connection
- **Technical Diagnostics** — Battery, WiFi signal, sock placement, skin temp, charging status
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
| **10** | Active Monitoring | hr=84–134, ox=99–100, bso=1. Best quality readings — sock properly placed and reading. |
| **6** | Signal Degraded | hr=0–130, ox=0–100. Mixed readings — sometimes valid, sometimes lost. 141 of 448 rows had ox=0. |

Observed state transitions: `7 → 1 → 10` (docked → calibrating → monitoring), `10 ↔ 1` (brief recalibrations during monitoring), `10 → 6 → 7` (signal loss → idle).

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

## Building a Standalone .exe

See [BUILDING.md](BUILDING.md) for instructions on creating a portable Windows executable using PyInstaller.

## Dependencies

- [pyowletapi](https://github.com/ryanbdclark/pyowletapi) — Owlet cloud API client
- [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) — Web server (web mode)
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — Modern desktop GUI (desktop mode)

## License

MIT — see [LICENSE](LICENSE) for details.
